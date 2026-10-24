"""Background jobs (design Q6, Q16): one active job per request, SKIP LOCKED pickup."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.models import Job, Result
from app.store.results import Expired, NotFound

ACTIVE = ("pending", "running")
RETENTION = timedelta(hours=24)
CANCELLED_MESSAGE = "This job was cancelled."


class JobExpired(Expired):
    """A finished job past its retention, or whose stored result has expired (410)."""


async def create(
    session: AsyncSession,
    *,
    request_key: str,
    request: dict[str, Any],
    plan: dict[str, Any],
    context: dict[str, Any],
    estimated_seconds: int,
    trace_id: uuid.UUID,
    client_ip: str | None,
) -> Job:
    """A new pending job, or the active job for the same request."""
    existing = await session.scalar(
        select(Job).where(Job.request_key == request_key, Job.status.in_(ACTIVE))
    )
    if existing is not None:
        return existing
    job = Job(
        job_id=uuid.uuid4(),
        request_key=request_key,
        request=request,
        plan=plan,
        context=context,
        estimated_seconds=estimated_seconds,
        trace_id=trace_id,
        client_ip=client_ip,
        status="pending",
        progress={},
    )
    session.add(job)
    await session.flush()
    return job


async def claim_next(session: AsyncSession, *, worker_id: str) -> Job | None:
    job = await session.scalar(
        select(Job)
        .where(Job.status == "pending")
        .order_by(Job.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status, job.locked_by = "running", worker_id
    job.started_at = job.heartbeat_at = datetime.now(UTC)
    job.attempts += 1
    await session.flush()
    return job


async def get(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    return await session.get(Job, job_id, populate_existing=True)


async def get_live(session: AsyncSession, job_id: uuid.UUID) -> tuple[Job, Result | None]:
    """A job and its stored result, expiring the same way results do (design Q14, Q17).

    `expires_at` is set when a job finishes. A succeeded job also expires with its result:
    its `result` would otherwise outlive the citations it points to.
    """
    job = await get(session, job_id)
    if job is None:
        raise NotFound(f"no job {job_id}")
    now = datetime.now(UTC)
    if job.expires_at is not None and job.expires_at <= now:
        raise JobExpired(f"job {job_id} has expired")
    result = None
    if job.result_id is not None:
        result = await session.get(Result, job.result_id)
        if result is None or result.expires_at <= now:
            raise JobExpired(f"the result of job {job_id} has expired")
    return job, result


async def progress(session: AsyncSession, job_id: uuid.UUID, value: dict[str, Any]) -> bool:
    """Record page progress. False when the job is no longer active: it was cancelled."""
    updated = await session.scalar(
        update(Job)
        .where(Job.job_id == job_id, Job.status.in_(ACTIVE))
        .values(progress=value, heartbeat_at=datetime.now(UTC))
        .returning(Job.job_id)
    )
    return updated is not None


async def status(session: AsyncSession, job_id: uuid.UUID) -> str | None:
    return await session.scalar(select(Job.status).where(Job.job_id == job_id))


async def cancel(session: AsyncSession, job_id: uuid.UUID) -> bool:
    """Cancel a pending or running job. False if it doesn't exist or has already finished.

    The row lock makes it safe against a worker claiming or finishing the job at the same
    moment; the worker notices the status and stops (design Q6).
    """
    job = await session.scalar(select(Job).where(Job.job_id == job_id).with_for_update())
    if job is None or job.status not in ACTIVE:
        return False
    now = datetime.now(UTC)
    job.status, job.finished_at, job.expires_at = "cancelled", now, now + RETENTION
    job.error = {
        "code": "cancelled",
        "message": CANCELLED_MESSAGE,
        "details": None,
        "trace_id": str(job.trace_id),
    }
    await session.flush()
    return True


async def heartbeat(session: AsyncSession, job_id: uuid.UUID) -> None:
    await session.execute(
        update(Job).where(Job.job_id == job_id).values(heartbeat_at=datetime.now(UTC))
    )


async def succeed(session: AsyncSession, job_id: uuid.UUID, *, result_id: uuid.UUID | None) -> bool:
    """False when the job was cancelled meanwhile: a finished job is never overwritten."""
    now = datetime.now(UTC)
    updated = await session.scalar(
        update(Job)
        .where(Job.job_id == job_id, Job.status.in_(ACTIVE))
        .values(
            status="succeeded", result_id=result_id, finished_at=now, expires_at=now + RETENTION
        )
        .returning(Job.job_id)
    )
    return updated is not None


async def fail(
    session: AsyncSession, job_id: uuid.UUID, *, error: dict[str, Any], retry: bool
) -> None:
    now = datetime.now(UTC)
    values: dict[str, Any] = (
        {"status": "pending", "locked_by": None, "error": error}
        if retry
        else {"status": "failed", "error": error, "finished_at": now, "expires_at": now + RETENTION}
    )
    # A cancelled job stays cancelled: neither failed nor queued for a retry.
    await session.execute(
        update(Job).where(Job.job_id == job_id, Job.status.in_(ACTIVE)).values(**values)
    )


async def requeue_stale(session: AsyncSession, *, older_than: timedelta) -> int:
    """Jobs whose worker stopped sending heartbeats (e.g. a restart) go back to pending.

    Only `running` jobs: a cancelled job is finished and never comes back.
    """
    stale = (
        await session.scalars(
            update(Job)
            .where(Job.status == "running", Job.heartbeat_at < datetime.now(UTC) - older_than)
            .values(status="pending", locked_by=None)
            .returning(Job.job_id)
        )
    ).all()
    return len(stale)


async def active_for_client(session: AsyncSession, client_ip: str) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.client_ip == client_ip, Job.status.in_(ACTIVE))
        )
        or 0
    )
