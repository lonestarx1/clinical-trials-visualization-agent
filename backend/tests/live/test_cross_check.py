"""Cross-check (design Q18): our aggregated counts vs the API's own counts. Opt-in: -m live.

Two independent methods must agree exactly: fetching trials and grouping them
ourselves, and asking the API to count each bucket.
"""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from app.ctgov.client import CtgovClient, RateLimiter
from app.ctgov.compiler import compile_filters
from app.ctgov.essie import Area, Phrase
from app.ctgov.retrieval import count_per_bucket
from app.pipeline.run import run_plan
from app.registry import DIMENSIONS
from app.registry.enums import Status
from app.schemas.plan import Filters, QueryPlan

pytestmark = pytest.mark.live
BASE = "https://clinicaltrials.gov/api/v2"
SCOPE = {"conditions": ["uveal melanoma"]}


@pytest.fixture
async def api() -> AsyncIterator[CtgovClient]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=5)) as http:
        yield CtgovClient(BASE, http, RateLimiter(40, 2))


def plan(**kw: Any) -> QueryPlan:
    base: dict[str, Any] = {
        "scope": "in_scope",
        "intent": "distribution",
        "chart_type": "bar_chart",
        "filters": SCOPE,
    }
    return QueryPlan.model_validate(base | kw)


async def test_status_buckets_match_the_api_counts(api: CtgovClient) -> None:
    ours = await run_plan(plan(dimension="status"), api, base_url=BASE)
    assert ours.visualization is not None
    mine = {r["status"]: r["trial_count"] for r in ours.visualization.data}

    theirs = await count_per_bucket(api, compile_filters(Filters(**SCOPE)), DIMENSIONS["status"])
    expected = {Status(code).label: n for code, n in theirs.buckets.items() if n}
    assert mine == expected
    assert ours.meta.unique_trials == theirs.total


async def test_country_bucket_matches_the_api_count(api: CtgovClient) -> None:
    ours = await run_plan(plan(intent="geographic", dimension="country"), api, base_url=BASE)
    assert ours.visualization is not None
    us = next(r for r in ours.visualization.data if r["country"] == "United States")
    search = compile_filters(Filters(**SCOPE)).narrow(
        Area("LocationCountry", Phrase("United States"))
    )
    assert us["trial_count"] == await api.count(search)
