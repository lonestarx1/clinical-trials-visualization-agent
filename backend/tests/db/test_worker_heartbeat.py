"""Workers keep a heartbeat while a job runs, and stalled jobs are requeued while the app runs."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.store import jobs
from app.store.models import Job
from app.workers import runner

pytestmark = pytest.mark.db
Sessions = async_sessionmaker[AsyncSession]


def fake_app(sessions: Sessions) -> Any:
    state = SimpleNamespace(
        sessions=sessions, llm_factory=lambda usage: None, ctgov=None, settings=None
    )
    return SimpleNamespace(state=state)


async def new_job(sessions: Sessions) -> uuid.UUID:
    async with sessions() as s:
        job = await jobs.create(
            s,
            request_key=uuid.uuid4().hex * 2,
            request={},
            plan={},
            context={},
            estimated_seconds=60,
            trace_id=uuid.uuid4(),
            client_ip=None,
        )
        await s.commit()
        return job.job_id


async def test_a_job_without_page_progress_still_sends_heartbeats(
    sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = await new_job(sessions)
    seen: dict[str, Any] = {}

    async def slow_job(job: uuid.UUID, **_: Any) -> None:
        await asyncio.sleep(0.45)  # e.g. per-year count calls: no page callbacks
        async with sessions() as s:
            row = await jobs.get(s, job)
            assert row is not None
            seen["gap"] = row.heartbeat_at - row.started_at  # type: ignore[operator]

    monkeypatch.setattr(runner, "run_job", slow_job)
    monkeypatch.setattr(runner, "HEARTBEAT_SECONDS", 0.1)
    assert await runner._process_one(fake_app(sessions), "w-test")
    assert seen["gap"] >= timedelta(seconds=0.2)
    async with sessions() as s:
        assert (await jobs.get(s, job_id)).status == "succeeded"  # type: ignore[union-attr]


async def test_a_job_stalled_by_a_restart_is_requeued_while_the_app_runs(
    sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = await new_job(sessions)
    async with sessions() as s:
        await jobs.claim_next(s, worker_id="gone")
        await s.execute(
            update(Job)
            .where(Job.job_id == job_id)
            .values(heartbeat_at=datetime.now(UTC) - timedelta(minutes=10))
        )
        await s.commit()

    async def quick_job(job: uuid.UUID, **_: Any) -> None:
        return None

    monkeypatch.setattr(runner, "run_job", quick_job)
    monkeypatch.setattr(runner, "REQUEUE_SECONDS", 0.1)
    worker = asyncio.create_task(runner.worker_loop(fake_app(sessions), 0))
    try:
        for _ in range(40):
            async with sessions() as s:
                job = await jobs.get(s, job_id)
            if job is not None and job.status == "succeeded":
                break
            await asyncio.sleep(0.1)
    finally:
        worker.cancel()
    assert job is not None and (job.status, job.attempts) == ("succeeded", 2)
