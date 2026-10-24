"""The mirror sync against real Postgres and a fake ClinicalTrials.gov (design Q22).

Run with: make test-db. Pages hold 2 trials here, so page tokens are followed.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ctgov import client as client_module
from app.ctgov.client import CtgovBadRequest
from app.mirror.slices import mirror_fields
from app.mirror.sync import sync
from app.store import mirror
from app.store.models import MirrorTrial, SyncRun
from tests.support.fake_registry import FakeRegistry, registry_client, trial

pytestmark = pytest.mark.db
Sessions = async_sessionmaker[AsyncSession]
D1, D2 = "2026-10-23T09:00:04", "2026-10-24T09:00:01"


@pytest.fixture(autouse=True)
def _small_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "PAGE_SIZE", 2)


def registry() -> FakeRegistry:
    return FakeRegistry(
        [
            trial("NCT1", "1998-05"),
            trial("NCT2", "2015-03"),
            trial("NCT3", "2015-07"),
            trial("NCT6", "2015-09"),
            trial("NCT4", None),
            trial("NCT5", "2031-01"),
        ],
        D1,
    )


async def mirrored(sessions: Sessions) -> dict[str, dict[str, Any]]:
    async with sessions() as s:
        rows = await s.scalars(select(MirrorTrial))
        return {r.nct_id: r.record for r in rows}


def searched(transport: Any) -> list[tuple[str, str, str]]:
    """(filter.advanced, fields, pageSize) of every /studies request."""
    return [
        (r.url.params.get("filter.advanced", ""), r.url.params["fields"], r.url.params["pageSize"])
        for r in transport.requests
        if r.url.path.endswith("/studies")
    ]


async def test_the_first_sync_loads_every_slice_and_marks_the_mirror_current(
    sessions: Sessions,
) -> None:
    fake = registry()
    client, transport = registry_client(fake)
    result = await sync(client, sessions)
    assert result is not None
    assert (result.kind, result.data_timestamp, result.upserted, result.removed) == (
        "load",
        D1,
        6,
        0,
    )
    assert set(await mirrored(sessions)) == set(fake.studies)
    async with sessions() as s:
        last = await mirror.last_success(s)
    assert last is not None and last.kind == "load"
    assert last.data_timestamp == datetime(2026, 10, 23, 9, 0, 4, tzinfo=UTC)
    y2015 = "AREA[StartDate]RANGE[2015-01-01,2015-12-31]"
    assert [p for p in searched(transport) if p[0] == y2015 and p[2] == "2"] == [
        (y2015, ",".join(mirror_fields()), "2")
    ] * 2  # 3 trials, 2 pages


async def test_a_current_mirror_makes_no_search_calls(sessions: Sessions) -> None:
    client, transport = registry_client(registry())
    await sync(client, sessions)
    transport.requests.clear()
    assert await sync(client, sessions) is None
    assert [r.url.path for r in transport.requests] == ["/api/v2/version"]


async def test_an_update_fetches_only_trials_changed_since_the_last_sync(
    sessions: Sessions,
) -> None:
    fake = registry()
    client, transport = registry_client(fake)
    await sync(client, sessions)
    async with sessions() as s:
        loaded = await mirror.last_success(s)
    assert loaded is not None
    fake.put(trial("NCT2", "2016-01", updated="2026-10-24"), trial("NCT7", "2015-01", "2026-10-24"))
    fake.data_timestamp = D2
    transport.requests.clear()

    result = await sync(client, sessions)
    assert result is not None
    assert (result.kind, result.data_timestamp, result.upserted, result.removed) == (
        "update",
        D2,
        2,
        0,
    )
    since = (loaded.started_at - timedelta(days=3)).date().isoformat()
    changed = f"AREA[LastUpdatePostDate]RANGE[{since},MAX]"
    full_pages = [p for p in searched(transport) if p[2] != "1"]
    assert {p[0] for p in full_pages} == {changed}  # no slice was downloaded again
    trials = await mirrored(sessions)
    assert trials["NCT2"]["protocolSection"]["statusModule"]["startDateStruct"]["date"] == (
        "2016-01"
    )
    assert "NCT7" in trials


async def test_removed_trials_are_found_by_slice_and_deleted(sessions: Sessions) -> None:
    fake = registry()
    client, transport = registry_client(fake)
    await sync(client, sessions)
    del fake.studies["NCT3"]
    fake.data_timestamp = D2
    transport.requests.clear()

    result = await sync(client, sessions)
    assert result is not None and (result.kind, result.removed) == ("update", 1)
    assert "NCT3" not in await mirrored(sessions)
    id_pages = {p[0] for p in searched(transport) if p[1] == "NCTId" and p[2] != "1"}
    assert id_pages == {
        "AREA[StartDate]RANGE[2015-01-01,2015-12-31]"
    }  # only the slice that differs


async def test_a_trial_missing_from_the_mirror_is_fetched_with_its_slice(
    sessions: Sessions,
) -> None:
    """A change that didn't bump LastUpdatePostDate (open item O5) is still caught."""
    fake = registry()
    client, _ = registry_client(fake)
    await sync(client, sessions)
    fake.put(trial("NCT8", "2015-02", updated="2026-09-01"))
    fake.data_timestamp = D2

    result = await sync(client, sessions)
    assert result is not None and result.kind == "update"
    assert "NCT8" in await mirrored(sessions)


async def test_a_failed_update_changes_nothing_and_is_recorded(sessions: Sessions) -> None:
    fake = registry()
    client, _ = registry_client(fake)
    await sync(client, sessions)
    fake.put(trial("NCT2", "2016-01", updated="2026-10-24"))
    fake.data_timestamp = D2
    fake.fail_after = fake.calls + 1  # the changed trials arrive, then the API fails

    with pytest.raises(CtgovBadRequest):
        await sync(client, sessions)
    trials = await mirrored(sessions)
    assert trials["NCT2"]["protocolSection"]["statusModule"]["startDateStruct"]["date"] == (
        "2015-03"
    )
    async with sessions() as s:
        last = await mirror.last_success(s)
        failed = await s.scalar(select(SyncRun).where(SyncRun.status == "failed"))
    assert last is not None and last.kind == "load"
    assert failed is not None and failed.kind == "update" and failed.finished_at is not None
    assert "HTTP 400" in (failed.error or "")


async def test_a_mirror_last_synced_over_a_week_ago_is_loaded_again(sessions: Sessions) -> None:
    fake = registry()
    client, _ = registry_client(fake)
    await sync(client, sessions)
    async with sessions() as s:
        await s.execute(update(SyncRun).values(started_at=datetime.now(UTC) - timedelta(days=8)))
        await s.commit()
    fake.data_timestamp = D2
    result = await sync(client, sessions)
    assert result is not None and result.kind == "load"


async def test_new_data_during_the_load_is_caught_up_before_the_mirror_is_current(
    sessions: Sessions,
) -> None:
    fake = registry()

    def new_update() -> None:
        fake.put(trial("NCT9", "2015-04", updated="2026-10-24"))
        fake.data_timestamp = D2

    fake.on_version = [lambda: None, new_update]  # the second read ends the load
    client, _ = registry_client(fake)
    result = await sync(client, sessions)
    assert result is not None
    assert (result.kind, result.data_timestamp) == ("load", D2)
    assert "NCT9" in await mirrored(sessions)
