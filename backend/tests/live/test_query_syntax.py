"""Live checks of compiled query syntax against the real API (opt-in: pytest -m live).

Verifies the syntax the probe didn't cover, and that escaping holds for real.
Counts drift daily, so assertions use ranges.
"""

from collections.abc import AsyncIterator

import httpx
import pytest

from app.ctgov.client import CtgovClient, RateLimiter
from app.ctgov.compiler import Search, compile_filters
from app.ctgov.retrieval import count_per_bucket
from app.registry import DIMENSIONS
from app.schemas.plan import Filters

pytestmark = pytest.mark.live


@pytest.fixture
async def api() -> AsyncIterator[CtgovClient]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=5)) as http:
        yield CtgovClient("https://clinicaltrials.gov/api/v2", http, RateLimiter(40, 2))


async def count(api: CtgovClient, **filters: object) -> int:
    return await api.count(compile_filters(Filters.model_validate(filters)))


async def test_strict_drug_count_matches_the_probe(api: CtgovClient) -> None:
    assert 2_500 <= await count(api, drugs=["pembrolizumab"]) <= 4_000  # probe: 2,652


async def test_injection_attempt_stays_a_phrase(api: CtgovClient) -> None:
    everything = await api.count(Search({}))
    injected = await count(api, conditions=['zzqx" OR ALL OR "zzqy'])
    assert everything > 500_000
    assert injected < 100


@pytest.mark.parametrize(
    "filters",
    [
        {"healthy_volunteers": True},
        {"has_results": True},
        {"age_groups": ["CHILD"]},
        {"sexes": ["FEMALE"]},
        {"allocations": ["RANDOMIZED"]},
        {"maskings": ["DOUBLE"]},
        {"primary_purposes": ["PREVENTION"]},
        {"sponsor_classes": ["INDUSTRY"]},
        {"countries": ["USA"]},
    ],
)
async def test_enum_and_boolean_filters_narrow_the_results(
    api: CtgovClient, filters: dict[str, object]
) -> None:
    n = await count(api, conditions=["melanoma"], **filters)
    total = await count(api, conditions=["melanoma"])
    assert 0 < n < total


async def test_broad_condition_matching_finds_at_least_as_many(api: CtgovClient) -> None:
    strict = await count(api, conditions=["lung cancer"])
    broad = await count(api, conditions=["lung cancer"], match_mode="broad")
    assert broad >= strict > 10_000  # probe: 13,423 quoted vs 14,657 unquoted


async def test_study_type_buckets_add_up_exactly(api: CtgovClient) -> None:
    search = compile_filters(Filters(conditions=["melanoma"]))
    result = await count_per_bucket(api, search, DIMENSIONS["study_type"])
    assert result.total > 1_000


async def test_version_has_a_data_timestamp(api: CtgovClient) -> None:
    assert (await api.version()).data_timestamp.startswith("20")
