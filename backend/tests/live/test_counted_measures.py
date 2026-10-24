"""Live checks for distinct_count and the per-year fast path. Opt-in: -m live.

Our answers are compared with an independent tally of the raw API records, fetched here
with plain httpx (not our client, extractor or aggregator).
"""

from collections import Counter, defaultdict
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from app.ctgov.client import CtgovClient, RateLimiter
from app.ctgov.compiler import compile_filters
from app.pipeline.run import run_plan
from app.schemas.plan import Filters, QueryPlan

pytestmark = pytest.mark.live
BASE = "https://clinicaltrials.gov/api/v2"
SCOPE: dict[str, Any] = {"drugs": ["pembrolizumab"], "start_year_min": 2015, "start_year_max": 2020}


@pytest.fixture
async def api() -> AsyncIterator[CtgovClient]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=5)) as http:
        yield CtgovClient(BASE, http, RateLimiter(40, 2))


async def raw_studies() -> list[dict[str, Any]]:
    params = compile_filters(Filters(**SCOPE)).params | {
        "fields": "NCTId,StartDate,LeadSponsorName",
        "pageSize": "1000",
    }
    studies: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30) as http:
        while True:
            body = (await http.get(f"{BASE}/studies", params=params)).json()
            studies += body.get("studies", [])
            if not body.get("nextPageToken"):
                return studies
            params["pageToken"] = body["nextPageToken"]


def year(study: dict[str, Any]) -> str:
    return str(study["protocolSection"]["statusModule"]["startDateStruct"]["date"][:4])


def plan(**kw: Any) -> QueryPlan:
    base = {
        "scope": "in_scope",
        "intent": "trend",
        "chart_type": "time_series",
        "dimension": "start_year",
        "filters": SCOPE,
    }
    return QueryPlan.model_validate(base | kw)


async def test_sponsors_with_three_or_more_trials_per_year_match_a_raw_tally(
    api: CtgovClient,
) -> None:
    p = plan(measure="distinct_count", options={"count_entity": "sponsor", "min_trials": 3})
    ours = await run_plan(p, api, base_url=BASE)
    assert ours.visualization is not None
    mine = {r["start_year"]: r["distinct_count"] for r in ours.visualization.data}

    per_year: dict[str, Counter[str]] = defaultdict(Counter)
    for s in await raw_studies():
        sponsor = s["protocolSection"]["sponsorCollaboratorsModule"]["leadSponsor"]["name"]
        per_year[year(s)][" ".join(sponsor.split()).casefold()] += 1
    expected = {
        str(y): sum(1 for n in per_year[str(y)].values() if n >= 3) for y in range(2015, 2021)
    }
    assert mine == expected
    assert any(expected.values())


async def test_counted_years_match_a_raw_tally(api: CtgovClient) -> None:
    ours = await run_plan(plan(), api, base_url=BASE)
    assert ours.visualization is not None
    assert "Counted with one ClinicalTrials.gov count per year" in " ".join(ours.meta.notes)
    mine = {r["start_year"]: r["trial_count"] for r in ours.visualization.data}

    tally = Counter(year(s) for s in await raw_studies())
    assert mine == {str(y): tally[str(y)] for y in range(2015, 2021)}
