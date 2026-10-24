"""The mirror's tables against real Postgres (design Q22). Run with: make test-db."""

import os
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.mirror.slices import YearSlice
from app.store import mirror
from app.store.db import create_engine

pytestmark = pytest.mark.db
Sessions = async_sessionmaker[AsyncSession]
TS = "2026-10-23T09:00:04"


def study(nct: str, start: str | None = "2015-03", updated: str = "2026-10-20") -> dict[str, Any]:
    status: dict[str, Any] = {"lastUpdatePostDateStruct": {"date": updated}}
    if start:
        status["startDateStruct"] = {"date": start}
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": f"Trial {nct}"},
            "statusModule": status,
        }
    }


async def test_upsert_inserts_then_replaces_records(sessions: Sessions) -> None:
    async with sessions() as s:
        assert await mirror.upsert_trials(s, [study("NCT1"), study("NCT2", start=None)]) == 2
        await mirror.upsert_trials(s, [study("NCT1", start="2016-01-05", updated="2026-10-23")])
        await s.commit()
    async with sessions() as s:
        assert await mirror.count_trials(s) == 2
        row = await s.get(mirror.MirrorTrial, "NCT1")
        assert row is not None
        assert (row.start_year, row.last_update_post_date) == (2016, date(2026, 10, 23))
        assert row.record["protocolSection"]["statusModule"]["startDateStruct"]["date"] == (
            "2016-01-05"
        )


async def test_counts_and_ids_per_slice_and_deletes(sessions: Sessions) -> None:
    async with sessions() as s:
        await mirror.upsert_trials(
            s, [study("NCT1", "1998-01"), study("NCT2", "2015-02"), study("NCT3", None)]
        )
        old, y2015, none = YearSlice(None, 1999), YearSlice(2015, 2015), YearSlice(None, None, True)
        assert [await mirror.count_in(s, sl) for sl in (old, y2015, none)] == [1, 1, 1]
        assert await mirror.ids_in(s, y2015) == {"NCT2"}
        assert await mirror.delete_trials(s, {"NCT2", "NCT9"}) == 1
        assert await mirror.count_in(s, y2015) == 0


async def test_the_last_successful_run_marks_the_mirror_current(sessions: Sessions) -> None:
    async with sessions() as s:
        assert await mirror.last_success(s) is None
        first = await mirror.start_run(s, kind="load", data_timestamp=TS)
        await mirror.finish_run(s, first, status="succeeded", upserted=3)
        failed = await mirror.start_run(
            s, kind="update", data_timestamp="2026-10-24T09:00:01", since=date(2026, 10, 20)
        )
        await mirror.finish_run(s, failed, status="failed", error="HTTP 503")
        await s.commit()
    async with sessions() as s:
        last = await mirror.last_success(s)
        assert last is not None
        assert (last.run_id, last.kind, last.upserted) == (first, "load", 3)
        assert last.data_timestamp == datetime(2026, 10, 23, 9, 0, 4, tzinfo=UTC)
        assert last.finished_at is not None


async def test_only_one_sync_holds_the_lock(sessions: Sessions) -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        async with engine.connect() as one, engine.connect() as two:
            assert await mirror.try_lock(one)
            assert not await mirror.try_lock(two)  # a second pod during a rolling update
            await mirror.unlock(one)
            assert await mirror.try_lock(two)
            await mirror.unlock(two)
    finally:
        await engine.dispose()
