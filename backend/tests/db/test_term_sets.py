"""Term sets against real Postgres and a fake ClinicalTrials.gov (design Q22). Run: make test-db."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.mirror.sync import sync
from app.mirror.terms import Term, term_set
from app.store.models import TermSet
from tests.support.fake_registry import FakeRegistry, registry_client, trial

pytestmark = pytest.mark.db
Sessions = async_sessionmaker[AsyncSession]
D1, D2 = "2026-10-23T09:00:04", "2026-10-24T09:00:01"
MELANOMA = Term("query.cond", '"melanoma"')


def searched(transport: Any) -> list[dict[str, str]]:
    return [dict(r.url.params) for r in transport.requests if r.url.path.endswith("/studies")]


async def loaded(sessions: Sessions) -> tuple[FakeRegistry, Any, Any]:
    fake = FakeRegistry([trial(f"NCT{i}", "2015-03") for i in range(1, 7)], D1)
    fake.terms[MELANOMA.key] = {"NCT1", "NCT2", "NCT3"}
    client, transport = registry_client(fake)
    await sync(client, sessions)
    transport.requests.clear()
    return fake, client, transport


async def test_a_term_is_resolved_once_then_reused_for_the_same_data(sessions: Sessions) -> None:
    _, client, transport = await loaded(sessions)
    assert await term_set(client, sessions, MELANOMA, data_timestamp=D1) == {"NCT1", "NCT2", "NCT3"}
    assert {p["query.cond"] for p in searched(transport)} == {'"melanoma"'}
    assert all(p["fields"] == "NCTId" for p in searched(transport))
    transport.requests.clear()

    assert await term_set(client, sessions, MELANOMA, data_timestamp=D1) == {"NCT1", "NCT2", "NCT3"}
    assert transport.requests == []
    async with sessions() as s:
        row = await s.get(TermSet, MELANOMA.key)
    assert row is not None and (row.size, row.param, row.expression) == (
        3,
        "query.cond",
        '"melanoma"',
    )


async def test_new_data_refreshes_a_set_from_the_changed_trials_only(sessions: Sessions) -> None:
    fake, client, transport = await loaded(sessions)
    await term_set(client, sessions, MELANOMA, data_timestamp=D1)
    async with sessions() as s:
        before = await s.get(TermSet, MELANOMA.key)
    assert before is not None

    # The daily update: NCT2 no longer matches, NCT5 now does; both records changed.
    fake.put(trial("NCT2", "2015-03", updated="2026-10-24"), trial("NCT5", "2015-03", "2026-10-24"))
    fake.terms[MELANOMA.key] = {"NCT1", "NCT3", "NCT5"}
    fake.data_timestamp = D2
    await sync(client, sessions)
    transport.requests.clear()

    assert await term_set(client, sessions, MELANOMA, data_timestamp=D2) == {"NCT1", "NCT3", "NCT5"}
    since = (before.checked_at - timedelta(days=3)).date().isoformat()
    assert (
        searched(transport)[0]["filter.advanced"] == f"AREA[LastUpdatePostDate]RANGE[{since},MAX]"
    )
    assert len(searched(transport)) == 1  # one small page: the changed trials that match
    async with sessions() as s:
        after = await s.get(TermSet, MELANOMA.key)
    assert after is not None
    assert after.resolved_at == before.resolved_at and after.checked_at > before.checked_at
    assert after.data_timestamp == datetime(2026, 10, 24, 9, 0, 1, tzinfo=UTC)


async def test_a_set_resolved_over_a_week_ago_is_resolved_again_in_full(sessions: Sessions) -> None:
    fake, client, transport = await loaded(sessions)
    await term_set(client, sessions, MELANOMA, data_timestamp=D1)
    async with sessions() as s:
        await s.execute(update(TermSet).values(resolved_at=datetime.now(UTC) - timedelta(days=8)))
        await s.commit()
    fake.terms[MELANOMA.key] = {"NCT1", "NCT4"}  # synonyms changed: no record did
    fake.data_timestamp = D2
    await sync(client, sessions)
    transport.requests.clear()

    assert await term_set(client, sessions, MELANOMA, data_timestamp=D2) == {"NCT1", "NCT4"}
    assert "filter.advanced" not in searched(transport)[0]


async def test_phrase_terms_in_the_advanced_filter_work_the_same(sessions: Sessions) -> None:
    fake, client, _ = await loaded(sessions)
    japan = Term("filter.advanced", 'AREA[LocationCountry]"Japan"')
    fake.terms[japan.key] = {"NCT6"}
    assert await term_set(client, sessions, japan, data_timestamp=D1) == {"NCT6"}
    async with sessions() as s:
        keys = set(await s.scalars(select(TermSet.term_key)))
    assert keys == {japan.key}
