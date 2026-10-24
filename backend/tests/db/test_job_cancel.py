"""DELETE /v1/jobs/{id} with Postgres: the row, the route and the real worker (design Q6, Q16).

The fake ClinicalTrials.gov below is slow on purpose (like the real one at 40 requests a
minute), so a job is still fetching when it is cancelled. Run with: make test-db.
"""

import asyncio
import os
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.main
from app.ctgov.client import CtgovClient, RateLimiter
from app.ctgov.compiler import Search
from app.main import create_app
from app.pipeline.query import StageLLMs
from app.store import jobs
from app.store.models import Job
from app.workers import runner
from tests.support.fake_llm import ScriptedLLM, text
from tests.support.fakes import json_response
from tests.support.recorded_api import BASE, VERSION

pytestmark = pytest.mark.db
Sessions = async_sessionmaker[AsyncSession]

PAGE_SECONDS = 0.15  # one page of the slow download
STOP_WITHIN = 1.6  # seconds: about one real page (~1.5 s at 40 requests a minute)

BY_PHASE = {
    "scope": "in_scope",
    "intent": "distribution",
    "chart_type": "bar_chart",
    "filters": {"conditions": ["cancer"]},
    "dimension": "phase",
}
PER_YEAR = {
    "scope": "in_scope",
    "intent": "trend",
    "chart_type": "time_series",
    "dimension": "start_year",
    "filters": {"start_year_min": 1970, "start_year_max": 2025},
}
NOTHING = BY_PHASE | {"filters": {"conditions": ["zzz no such condition"]}}


Sent = list[tuple[float, httpx.Request]]


def slow_registry(requests: Sent) -> CtgovClient:
    """Every search matches 200,000 trials (except "zzz"), and pages never run out."""

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append((time.monotonic(), request))
        if request.url.path.endswith("/version"):
            return json_response(VERSION)
        await asyncio.sleep(PAGE_SECONDS)
        total = 0 if "zzz" in str(request.url) else 200_000
        if request.url.params.get("pageSize") == "1":
            return json_response({"studies": [], "totalCount": total})
        return json_response({"studies": [], "totalCount": total, "nextPageToken": "more"})

    return CtgovClient(
        BASE,
        http=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        limiter=RateLimiter(60_000, 2),
        max_attempts=1,
    )


def fake_app(sessions: Sessions, ctgov: CtgovClient, monkeypatch: pytest.MonkeyPatch) -> Any:
    from app.core.config import Settings

    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")

    def llms(usage: Any) -> StageLLMs:
        narrator = ScriptedLLM(text({"title": "Trials"}), stage="narrator")
        return StageLLMs(ScriptedLLM(), ScriptedLLM(), narrator)

    state = SimpleNamespace(sessions=sessions, llm_factory=llms, ctgov=ctgov, settings=Settings())
    return SimpleNamespace(state=state)


async def new_job(sessions: Sessions, plan: dict[str, Any] | None = None) -> uuid.UUID:
    async with sessions() as s:
        job = await jobs.create(
            s,
            request_key=uuid.uuid4().hex * 2,
            request={"query": "Trials by phase", "citations_per_datum": 1},
            plan=plan or BY_PHASE,
            context={
                "guard": {"verdict": "ok", "model": "fake"},
                "planner": {"steps": 1, "tool_calls": [], "model": "fake"},
                "warnings": [],
                "chart_type_source": "ai",
                "cache": {"plan": "miss", "result": "miss"},
                "trace_id": str(uuid.uuid4()),
            },
            estimated_seconds=900,
            trace_id=uuid.uuid4(),
            client_ip=None,
        )
        await s.commit()
        return job.job_id


async def row(sessions: Sessions, job_id: uuid.UUID) -> Job:
    async with sessions() as s:
        job = await jobs.get(s, job_id)
    assert job is not None
    return job


async def wait_for(sessions: Sessions, job_id: uuid.UUID, done: Any, seconds: float = 10) -> Job:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        job = await row(sessions, job_id)
        if done(job):
            return job
        await asyncio.sleep(0.05)
    raise AssertionError(f"job {job_id} never got there: {job.status} {job.progress}")


async def cancel(sessions: Sessions, job_id: uuid.UUID) -> float:
    async with sessions() as s:
        await jobs.cancel(s, job_id)
        await s.commit()
    return time.monotonic()


# ---------- the worker ----------


async def test_a_downloading_job_stops_within_a_page_and_frees_the_worker(
    sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: Sent = []
    ctgov = slow_registry(requests)
    first = await new_job(sessions)
    worker = asyncio.create_task(runner.worker_loop(fake_app(sessions, ctgov, monkeypatch), 1))
    try:
        await wait_for(sessions, first, lambda j: (j.progress.get("pages_done") or 0) >= 3)
        cancelled_at = await cancel(sessions, first)
        second = await new_job(sessions, NOTHING)  # the worker is free for the next job
        await wait_for(sessions, second, lambda j: j.status == "succeeded")
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)

    job = await row(sessions, first)
    assert (job.status, job.attempts, job.error["code"]) == ("cancelled", 1, "cancelled")  # type: ignore[index]
    pages = [at for at, r in requests if at > cancelled_at and r.url.params.get("pageToken")]
    assert len(pages) <= 2, "kept downloading after the cancel"
    assert max(pages, default=cancelled_at) - cancelled_at < STOP_WITHIN


async def test_the_worker_returns_within_a_page_of_the_cancel(
    sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = await new_job(sessions)
    fake = fake_app(sessions, slow_registry([]), monkeypatch)
    work = asyncio.create_task(runner._process_one(fake, "w-test"))
    await wait_for(sessions, job_id, lambda j: (j.progress.get("pages_done") or 0) >= 2)
    frozen = (await row(sessions, job_id)).progress
    cancelled_at = await cancel(sessions, job_id)
    assert await asyncio.wait_for(work, timeout=5) is True
    took = time.monotonic() - cancelled_at
    print(f"download path stopped {took:.2f}s after the cancel")
    assert took < STOP_WITHIN
    job = await row(sessions, job_id)
    assert job.status == "cancelled" and job.result_id is None
    assert job.progress["pages_done"] - frozen["pages_done"] <= 2  # no progress writes after


async def test_counting_per_year_stops_promptly_too(
    sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counting trials per year reports no page progress; the job still stops."""
    requests: Sent = []
    job_id = await new_job(sessions, PER_YEAR)
    fake = fake_app(sessions, slow_registry(requests), monkeypatch)
    work = asyncio.create_task(runner._process_one(fake, "w-test"))
    await wait_for(sessions, job_id, lambda j: j.status == "running")
    await asyncio.sleep(1.0)  # well into the ~170 count calls
    assert not (await row(sessions, job_id)).progress  # no page progress on this path
    cancelled_at = await cancel(sessions, job_id)
    assert await asyncio.wait_for(work, timeout=5) is True
    took = time.monotonic() - cancelled_at
    print(f"per-year path stopped {took:.2f}s after the cancel")
    assert took < STOP_WITHIN
    sent = len(requests)
    await asyncio.sleep(0.5)
    assert len(requests) == sent, "count calls kept going after the cancel"
    assert (await row(sessions, job_id)).status == "cancelled"


async def test_a_cancelled_job_is_never_overwritten_retried_or_requeued(
    sessions: Sessions,
) -> None:
    job_id = await new_job(sessions)
    async with sessions() as s:
        await jobs.claim_next(s, worker_id="gone")
        await s.commit()
    await cancel(sessions, job_id)
    async with sessions() as s:
        await jobs.fail(s, job_id, error={"code": "upstream_unavailable"}, retry=True)
        await jobs.fail(s, job_id, error={"code": "internal_error"}, retry=False)
        assert not await jobs.succeed(s, job_id, result_id=None)
        await s.execute(
            update(Job)
            .where(Job.job_id == job_id)
            .values(heartbeat_at=datetime.now(UTC) - timedelta(hours=1))
        )
        assert await jobs.requeue_stale(s, older_than=timedelta(minutes=2)) == 0
        assert await jobs.claim_next(s, worker_id="w-2") is None
        await s.commit()
    job = await row(sessions, job_id)
    assert (job.status, job.error["code"], job.attempts) == ("cancelled", "cancelled", 1)  # type: ignore[index]


async def test_the_registry_client_still_works_after_a_cancel(
    sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Requests cancelled while queued in the shared rate limiter must not keep their slots."""
    ctgov = slow_registry([])
    job_id = await new_job(sessions, PER_YEAR)
    work = asyncio.create_task(runner._process_one(fake_app(sessions, ctgov, monkeypatch), "w"))
    await wait_for(sessions, job_id, lambda j: j.status == "running")
    await asyncio.sleep(0.5)
    await cancel(sessions, job_id)
    await asyncio.wait_for(work, timeout=5)
    count = ctgov.count(Search({"query.cond": "cancer"}))
    assert await asyncio.wait_for(count, timeout=2) == 200_000


# ---------- the route ----------


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, sessions: Sessions) -> Iterator[TestClient]:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("DATABASE_URL", os.environ["DATABASE_URL"])
    monkeypatch.setattr(app.main, "worker_loop", _idle_worker)  # keep the test's jobs pending
    with TestClient(create_app()) as c:
        yield c


async def _idle_worker(app: Any, index: int) -> None:
    await asyncio.Event().wait()


async def test_delete_cancels_a_pending_job_and_is_idempotent(
    client: TestClient, sessions: Sessions
) -> None:
    job_id = await new_job(sessions)
    first = client.delete(f"/v1/jobs/{job_id}")
    assert first.status_code == 200
    body = first.json()
    assert body["job_id"] == str(job_id)
    assert body["status"] == "cancelled" and body["result"] is None
    assert body["error"]["code"] == "cancelled"
    assert body["error"]["trace_id"]
    again = client.delete(f"/v1/jobs/{job_id}")
    assert (again.status_code, again.json()) == (200, body)
    polled = client.get(f"/v1/jobs/{job_id}")
    assert (polled.status_code, polled.json()) == (200, body)
    async with sessions() as s:
        assert await jobs.claim_next(s, worker_id="w") is None


async def test_delete_leaves_a_finished_job_unchanged(
    client: TestClient, sessions: Sessions
) -> None:
    job_id = await new_job(sessions)
    async with sessions() as s:
        await jobs.claim_next(s, worker_id="w")
        await jobs.fail(s, job_id, error={"code": "upstream_unavailable"}, retry=False)
        await s.commit()
    before = client.get(f"/v1/jobs/{job_id}").json()
    response = client.delete(f"/v1/jobs/{job_id}")
    assert (response.status_code, response.json()) == (200, before)
    assert before["status"] == "failed"


def test_delete_an_unknown_job_is_not_found(client: TestClient) -> None:
    response = client.delete(f"/v1/jobs/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_a_cancelled_question_can_be_asked_again(sessions: Sessions) -> None:
    """A cancelled job is not active: the same request starts a new job."""
    async with sessions() as s:
        key = uuid.uuid4().hex * 2
        args: dict[str, Any] = dict(
            request_key=key,
            request={},
            plan={},
            context={},
            estimated_seconds=60,
            trace_id=uuid.uuid4(),
            client_ip="203.0.113.9",
        )
        first = await jobs.create(s, **args)
        await s.commit()
        await jobs.cancel(s, first.job_id)
        await s.commit()
        assert await jobs.active_for_client(s, "203.0.113.9") == 0
        second = await jobs.create(s, **args)
        await s.commit()
    assert second.job_id != first.job_id
