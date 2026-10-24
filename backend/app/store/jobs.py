"""Background jobs (design Q6, Q16): one active job per request, SKIP LOCKED pickup."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.models import Job

ACTIVE = ("pending", "running")
RETENTION = timedelta(hours=24)


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


async def progress(session: AsyncSession, job_id: uuid.UUID, value: dict[str, Any]) -> None:
    await session.execute(
        update(Job)
        .where(Job.job_id == job_id)
        .values(progress=value, heartbeat_at=datetime.now(UTC))
    )


async def heartbeat(session: AsyncSession, job_id: uuid.UUID) -> None:
    await session.execute(
        update(Job).where(Job.job_id == job_id).values(heartbeat_at=datetime.now(UTC))
    )


async def succeed(session: AsyncSession, job_id: uuid.UUID, *, result_id: uuid.UUID | None) -> None:
    now = datetime.now(UTC)
    await session.execute(
        update(Job)
        .where(Job.job_id == job_id)
        .values(
            status="succeeded", result_id=result_id, finished_at=now, expires_at=now + RETENTION
        )
    )


async def fail(
    session: AsyncSession, job_id: uuid.UUID, *, error: dict[str, Any], retry: bool
) -> None:
    now = datetime.now(UTC)
    values: dict[str, Any] = (
        {"status": "pending", "locked_by": None, "error": error}
        if retry
        else {"status": "failed", "error": error, "finished_at": now, "expires_at": now + RETENTION}
    )
    await session.execute(update(Job).where(Job.job_id == job_id).values(**values))


async def requeue_stale(session: AsyncSession, *, older_than: timedelta) -> int:
    """Jobs whose worker stopped sending heartbeats (e.g. a restart) go back to pending."""
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
