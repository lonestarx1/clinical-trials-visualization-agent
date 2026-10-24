"""Cross-check (design Q22): the mirror's counts vs the live API's, filter by filter.

Opt-in: -m live, with MIRROR_DATABASE_URL pointing at a loaded mirror that is current (its last
sync matches the API's data timestamp). About 100 count calls and a few term listings.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ctgov.client import CtgovClient, RateLimiter
from app.ctgov.compiler import Search, compile_filters
from app.mirror import query
from app.mirror.terms import split, term_set
from app.registry import enums as e
from app.schemas.plan import Filters
from app.store import mirror
from app.store.db import create_engine

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif("MIRROR_DATABASE_URL" not in os.environ, reason="needs a loaded mirror"),
]
BASE = "https://clinicaltrials.gov/api/v2"

ENUM_FILTERS: dict[str, type[e.LabelledEnum]] = {
    "phases": e.Phase,
    "statuses": e.Status,
    "study_types": e.StudyType,
    "sponsor_classes": e.AgencyClass,
    "age_groups": e.StandardAge,
    "sexes": e.Sex,
    "allocations": e.Allocation,
    "maskings": e.Masking,
    "primary_purposes": e.PrimaryPurpose,
}
STRUCTURED: list[dict[str, Any]] = [
    *({name: [value.value]} for name, enum in ENUM_FILTERS.items() for value in enum),
    {"healthy_volunteers": True},
    {"healthy_volunteers": False},
    {"has_results": True},
    {"has_results": False},
    {"start_year_max": 1999},
    *({"start_year_min": y, "start_year_max": y} for y in range(2000, 2029)),
    {"start_year_min": 2029},
    {"phases": ["PHASE2", "PHASE3"], "statuses": ["RECRUITING"], "start_year_min": 2020},
]
WITH_TERMS: list[dict[str, Any]] = [
    {"conditions": ["breast cancer"]},
    {"conditions": ["breast cancer"], "phases": ["PHASE3"], "start_year_min": 2015},
    {"drugs": ["Keytruda"], "statuses": ["RECRUITING"]},
    {"sponsors": ["Pfizer"], "has_results": True},
    {"countries": ["Japan"], "conditions": ["breast cancer"]},
    {"conditions": ["lung cancer"], "match_mode": "broad"},
]


@pytest.fixture
async def api() -> AsyncIterator[CtgovClient]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=5)) as http:
        yield CtgovClient(BASE, http, RateLimiter(54, 9, burst=9), version_ttl=0)


@pytest.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(os.environ["MIRROR_DATABASE_URL"])
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def mismatches(
    api: CtgovClient, sessions: async_sessionmaker[AsyncSession], cases: list[dict[str, Any]]
) -> list[str]:
    version = await api.version()
    async with sessions() as s:
        last = await mirror.last_success(s)
    assert last is not None, "the mirror was never loaded"
    assert last.data_timestamp.replace(tzinfo=None).isoformat() == version.data_timestamp, (
        "the mirror is not current: sync it first"
    )
    searches: list[Search] = [compile_filters(Filters.model_validate(c)) for c in cases]
    for search in searches:  # term sets first, so the mirror can answer
        terms, _ = split(search) or ([], [])
        for values in terms:
            for term in values:
                await term_set(api, sessions, term, data_timestamp=version.data_timestamp)
    live = await asyncio.gather(*(api.count(s) for s in searches))
    found = []
    for case, search, expected in zip(cases, searches, live, strict=True):
        async with sessions() as s:
            got = await query.count(s, search)
        if got != expected:
            found.append(f"{case}: mirror {got}, API {expected}")
    return found


async def test_every_structured_filter_counts_the_same_as_the_api(
    api: CtgovClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    assert await mismatches(api, sessions, STRUCTURED) == []


async def test_terms_and_filters_together_count_the_same_as_the_api(
    api: CtgovClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    assert await mismatches(api, sessions, WITH_TERMS) == []
