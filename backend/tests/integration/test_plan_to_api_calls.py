"""Hand-written plans -> the exact ClinicalTrials.gov calls, served with recorded real studies.

M1a exit check: a QueryPlan becomes the correct API requests, and the fetched
trials come back intact.
"""

from typing import Any

import httpx

from app.ctgov.client import CtgovClient, RateLimiter
from app.ctgov.compiler import compile_plan
from app.ctgov.retrieval import fields_for
from app.schemas.plan import QueryPlan
from tests.support.fakes import FakeClock, RecordingTransport, json_response
from tests.support.samples import load_sample, sample_names

BASE = "https://clinicaltrials.gov/api/v2"


def recorded_page(_: httpx.Request) -> httpx.Response:
    studies = [load_sample(name) for name in sample_names()]
    return json_response({"studies": studies, "totalCount": len(studies)})


def client() -> tuple[CtgovClient, RecordingTransport]:
    clock = FakeClock()
    transport = RecordingTransport(recorded_page)
    return (
        CtgovClient(
            BASE,
            http=httpx.AsyncClient(transport=transport),
            limiter=RateLimiter(40, 2, clock=clock),
            clock=clock,
        ),
        transport,
    )


async def run(plan: dict[str, Any]) -> list[dict[str, str]]:
    query_plan = QueryPlan.model_validate(plan)
    api, transport = client()
    for search in compile_plan(query_plan):
        result = await api.fetch_all(search, fields_for(query_plan))
        assert len(result.studies) == len(sample_names())
    return [dict(r.url.params) for r in transport.requests]


async def test_pa3_breast_cancer_by_phase() -> None:
    calls = await run(
        {
            "scope": "in_scope",
            "intent": "distribution",
            "chart_type": "bar_chart",
            "filters": {"conditions": ["breast cancer"]},
            "dimension": "phase",
        }
    )
    assert calls == [
        {
            "query.cond": '"breast cancer"',
            "fields": "NCTId,BriefTitle,Phase,StudyType",
            "pageSize": "1000",
            "countTotal": "true",
        }
    ]


async def test_pa5_pembrolizumab_vs_nivolumab_phases() -> None:
    calls = await run(
        {
            "scope": "in_scope",
            "intent": "comparison",
            "chart_type": "grouped_bar_chart",
            "groups": [
                {"label": "Pembrolizumab", "filters": {"drugs": ["pembrolizumab"]}},
                {"label": "Nivolumab", "filters": {"drugs": ["nivolumab"]}},
            ],
            "dimension": "phase",
        }
    )
    assert [c["filter.advanced"] for c in calls] == [
        'AREA[InterventionNameSearch]"pembrolizumab"',
        'AREA[InterventionNameSearch]"nivolumab"',
    ]
    assert all(c["fields"] == "NCTId,BriefTitle,Phase,StudyType" for c in calls)


async def test_pa7_recruiting_lung_cancer_trials_by_country() -> None:
    calls = await run(
        {
            "scope": "in_scope",
            "intent": "geographic",
            "chart_type": "bar_chart",
            "filters": {"conditions": ["lung cancer"], "statuses": ["RECRUITING"]},
            "dimension": "country",
            "options": {"top_n": 10},
        }
    )
    assert calls == [
        {
            "query.cond": '"lung cancer"',
            "filter.overallStatus": "RECRUITING",
            "fields": "NCTId,BriefTitle,LocationCountry",
            "pageSize": "1000",
            "countTotal": "true",
        }
    ]
