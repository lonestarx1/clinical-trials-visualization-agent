"""Repositories against real Postgres (design Q14, Q16). Run with: make test-db."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.client import LLMCall, UsageLog
from app.store import jobs, results, usage
from app.store.models import Job, ResultCitation, ResultDatum

pytestmark = pytest.mark.db
Sessions = async_sessionmaker[AsyncSession]


def citation(i: int) -> dict:
    return {
        "nct_id": f"NCT{i:08d}",
        "url": f"https://clinicaltrials.gov/study/NCT{i:08d}",
        "title": f"Trial {i}",
        "evidence": [{"field": "x", "excerpt": i}],
    }


async def save(sessions: Sessions, key: str = "k" * 64, n: int = 7) -> uuid.UUID:
    async with sessions() as s:
        result_id = await results.save_result(
            s,
            result_key=key,
            response={"status": "ok", "visualization": {"data": []}, "meta": {}},
            request={"query": "q"},
            plan={"dimension": "phase"},
            datums=[results.Datum("PHASE2", "Phase 2", 7.0, [citation(i) for i in range(n)])],
            searches=[{"params": {"query.cond": '"x"'}, "total_count": n}],
            data_timestamp="2026-10-23T09:00:04",
            api_version="2.0.5",
            ttl=timedelta(hours=24),
        )
        await s.commit()
    return result_id


async def test_full_citations_page_by_rank(sessions: Sessions) -> None:
    result_id = await save(sessions)
    async with sessions() as s:
        first = await results.citation_page(s, result_id, "PHASE2", after=None, limit=3)
        assert [c["nct_id"] for c in first.citations] == [
            "NCT00000000",
            "NCT00000001",
            "NCT00000002",
        ]
        assert (first.citation_count, first.next_cursor, first.label) == (7, 3, "Phase 2")
        last = await results.citation_page(s, result_id, "PHASE2", after=6, limit=3)
        assert [c["nct_id"] for c in last.citations] == ["NCT00000006"]
        assert last.next_cursor is None


async def test_unknown_and_expired_results(sessions: Sessions) -> None:
    async with sessions() as s:
        with pytest.raises(results.NotFound):
            await results.citation_page(s, uuid.uuid4(), "PHASE2", after=None, limit=3)
    result_id = await save(sessions)
    async with sessions() as s:
        with pytest.raises(results.NotFound):
            await results.citation_page(s, result_id, "PHASE9", after=None, limit=3)
        await results.expire_now(s, result_id)
        await s.commit()
        with pytest.raises(results.Expired):
            await results.citation_page(s, result_id, "PHASE2", after=None, limit=3)


async def test_deleting_a_result_cascades(sessions: Sessions) -> None:
    result_id = await save(sessions)
    async with sessions() as s:
        await results.delete(s, result_id)
        await s.commit()
        assert await s.scalar(select(func.count()).select_from(ResultDatum)) == 0
        assert await s.scalar(select(func.count()).select_from(ResultCitation)) == 0


async def test_latest_result_for_a_key(sessions: Sessions) -> None:
    await save(sessions, key="a" * 64)
    newer = await save(sessions, key="a" * 64)
    async with sessions() as s:
        found = await results.latest_valid(s, "a" * 64)
        assert found is not None and found.result_id == newer


async def test_usage_is_recorded_and_summed_per_day(sessions: Sessions) -> None:
    log = UsageLog(
        [
            LLMCall("planner", "gpt-5.4-mini", False, 1000, 0, 200, 50, 0.0012, 900),
            LLMCall("guard", "gpt-5.4-nano", False, 300, 0, 10, 0, None, 200),
        ]
    )
    async with sessions() as s:
        await usage.record(s, log, trace_id=uuid.uuid4(), job_id=None, price_version="1")
        await s.commit()
        assert await usage.spent_today(s) == Decimal("0.0012")
        summary = await usage.summary(s, day=datetime.now(UTC).date())
        assert summary["calls"] == 2 and summary["unknown_cost_calls"] == 1
        assert summary["by_model"]["gpt-5.4-mini"]["cost_usd"] == pytest.approx(0.0012)


async def test_one_active_job_per_request(sessions: Sessions) -> None:
    async with sessions() as s:
        first = await jobs.create(
            s,
            request_key="r" * 64,
            request={},
            plan={},
            context={},
            estimated_seconds=90,
            trace_id=uuid.uuid4(),
            client_ip="1.2.3.4",
        )
        await s.commit()
        again = await jobs.create(
            s,
            request_key="r" * 64,
            request={},
            plan={},
            context={},
            estimated_seconds=90,
            trace_id=uuid.uuid4(),
            client_ip="1.2.3.4",
        )
        assert again.job_id == first.job_id  # duplicate request reuses the active job
        s.add(
            Job(
                job_id=uuid.uuid4(),
                request_key="r" * 64,
                request={},
                plan={},
                context={},
                estimated_seconds=1,
                trace_id=uuid.uuid4(),
            )
        )
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_workers_claim_each_job_once(sessions: Sessions) -> None:
    async with sessions() as s:
        created = await jobs.create(
            s,
            request_key="j" * 64,
            request={},
            plan={},
            context={},
            estimated_seconds=90,
            trace_id=uuid.uuid4(),
            client_ip=None,
        )
        await s.commit()
    async with sessions() as a, sessions() as b:
        claimed = await jobs.claim_next(a, worker_id="w1")
        assert claimed is not None and claimed.job_id == created.job_id
        assert await jobs.claim_next(b, worker_id="w2") is None  # locked / already running
        await a.commit()
    async with sessions() as s:
        job = await jobs.get(s, created.job_id)
        assert job is not None and (job.status, job.locked_by, job.attempts) == ("running", "w1", 1)
        await jobs.progress(
            s, created.job_id, {"stage": "retrieve", "pages_done": 2, "pages_total": 9}
        )
        await jobs.succeed(s, created.job_id, result_id=None)
        await s.commit()
        job = await jobs.get(s, created.job_id)
        assert job is not None and job.status == "succeeded" and job.finished_at is not None


async def test_active_jobs_per_client(sessions: Sessions) -> None:
    async with sessions() as s:
        for i in range(3):
            await jobs.create(
                s,
                request_key=str(i) * 64,
                request={},
                plan={},
                context={},
                estimated_seconds=1,
                trace_id=uuid.uuid4(),
                client_ip="9.9.9.9",
            )
        await s.commit()
        assert await jobs.active_for_client(s, "9.9.9.9") == 3
