"""Cancelling a background job: the work stops promptly, and the worker writes nothing after.

The database side (the route, the row, the real worker loop) is in tests/db/test_job_cancel.py.
"""

import asyncio
import time
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.pipeline.query import JobCancelled, stop_when_cancelled
from app.pipeline.run import gather_or_cancel
from app.workers import runner


async def test_the_work_finishes_normally_when_nobody_cancels() -> None:
    async def work() -> str:
        await asyncio.sleep(0.05)
        return "done"

    async def never() -> bool:
        return False

    assert await stop_when_cancelled(work(), never, every=0.01) == "done"


async def test_cancelled_work_stops_within_one_check() -> None:
    stopped = asyncio.Event()
    cancelled_at: list[float] = []

    async def endless() -> None:
        try:
            await asyncio.sleep(60)  # e.g. 120 per-year count calls waiting their turn
        except asyncio.CancelledError:
            stopped.set()
            raise

    async def cancelled() -> bool:
        if not cancelled_at:
            cancelled_at.append(time.monotonic())
            return False
        return True

    with pytest.raises(JobCancelled):
        await stop_when_cancelled(endless(), cancelled, every=0.05)
    assert stopped.is_set()
    assert time.monotonic() - cancelled_at[0] < 0.5


async def test_an_error_from_the_work_is_not_hidden() -> None:
    async def broken() -> None:
        raise ValueError("boom")

    async def never() -> bool:
        return False

    with pytest.raises(ValueError):
        await stop_when_cancelled(broken(), never, every=0.01)


async def test_a_failing_check_does_not_stop_the_work() -> None:
    """A database blip while checking must not turn into a failed job."""

    async def work() -> int:
        await asyncio.sleep(0.1)
        return 42

    async def flaky() -> bool:
        raise ConnectionError("database briefly down")

    assert await stop_when_cancelled(work(), flaky, every=0.01) == 42


async def test_gather_or_cancel_stops_the_other_downloads_when_one_fails() -> None:
    """A compare question downloads each group at once; one stopping must stop the others."""
    other = asyncio.Event()

    async def stops() -> None:
        await asyncio.sleep(0.01)
        raise JobCancelled

    async def slow() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            other.set()
            raise

    with pytest.raises(JobCancelled):
        await gather_or_cancel(stops(), slow())
    await asyncio.sleep(0)
    assert other.is_set()


async def test_gather_or_cancel_returns_results_in_order() -> None:
    async def value(n: int) -> int:
        await asyncio.sleep(0.01 * (3 - n))
        return n

    assert await gather_or_cancel(value(1), value(2)) == [1, 2]


# ---------- the worker ----------


class FakeSession:
    async def commit(self) -> None:
        return None

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None


def fake_app() -> Any:
    state = SimpleNamespace(
        sessions=FakeSession, llm_factory=lambda usage: None, ctgov=None, settings=None
    )
    return SimpleNamespace(state=state)


async def test_the_worker_writes_nothing_for_a_cancelled_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not failed, not retried, not succeeded: the row already says `cancelled`."""
    writes: list[str] = []
    job = SimpleNamespace(job_id=uuid.uuid4(), attempts=1, max_attempts=3, trace_id=uuid.uuid4())

    async def claim(_: Any, **__: Any) -> Any:
        return job

    async def cancelled_run(*_: Any, **__: Any) -> None:
        raise JobCancelled

    async def fail(*_: Any, **kw: Any) -> None:
        writes.append(f"fail retry={kw['retry']}")

    async def succeed(*_: Any, **__: Any) -> bool:
        writes.append("succeed")
        return True

    monkeypatch.setattr(runner.jobs, "claim_next", claim)
    monkeypatch.setattr(runner.jobs, "fail", fail)
    monkeypatch.setattr(runner.jobs, "succeed", succeed)
    monkeypatch.setattr(runner, "run_job", cancelled_run)
    assert await runner._process_one(fake_app(), "w-test") is True
    assert writes == []


def test_cancelled_is_never_retryable() -> None:
    assert not issubclass(JobCancelled, runner.RETRYABLE)
