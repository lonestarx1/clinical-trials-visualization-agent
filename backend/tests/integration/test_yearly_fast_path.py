"""Trials per year through the real client: count calls and sample pages, no full download."""

from typing import Any

import httpx

from app.pipeline.run import run_plan
from app.schemas.plan import QueryPlan
from tests.support.fakes import json_response
from tests.support.recorded_api import BASE, VERSION, recorded_client

Y15 = "AREA[StartDate]RANGE[2015-01-01,2015-12-31]"
Y16 = "AREA[StartDate]RANGE[2016-01-01,2016-12-31]"
SPAN = "AREA[StartDate]RANGE[2015-01-01,2016-12-31]"
EST = "AREA[StartDateType]ESTIMATED"


def study(nct: str, date: str) -> dict[str, Any]:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": f"Trial {nct}"},
            "statusModule": {"startDateStruct": {"date": date, "type": "ACTUAL"}},
        }
    }


SAMPLES = {Y15: [study("N1", "2015-12-31")], Y16: [study("N2", "2016-11-02")]}


def handler(year_2016: int):  # type: ignore[no-untyped-def]
    counts = {
        SPAN: 30,
        f"({SPAN} AND {SPAN})": 30,
        f"({SPAN} AND {Y15})": 10,
        f"({SPAN} AND {Y16})": year_2016,
        f"(({SPAN} AND {Y15}) AND {EST})": 1,
        f"(({SPAN} AND {Y16}) AND {EST})": 0,
    }

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/version"):
            return json_response(VERSION)
        advanced = request.url.params.get("filter.advanced", "")
        if request.url.params.get("countTotal") == "true" and request.url.params["pageSize"] == "1":
            return json_response({"studies": [], "totalCount": counts[advanced]})
        if request.url.params["pageSize"] == "1000":  # the full download (fallback)
            every = [s for page in SAMPLES.values() for s in page]
            return json_response({"studies": every, "totalCount": len(every)})
        year = Y15 if Y15 in advanced else Y16
        return json_response({"studies": SAMPLES[year]})

    return respond


PLAN = QueryPlan.model_validate(
    {
        "scope": "in_scope",
        "intent": "trend",
        "chart_type": "time_series",
        "dimension": "start_year",
        "filters": {"start_year_min": 2015, "start_year_max": 2016},
    }
)


async def test_years_are_counted_not_downloaded() -> None:
    client, transport = recorded_client(handler(year_2016=20))
    response = await run_plan(PLAN, client, base_url=BASE, citations_per_datum=2)
    rows = response.visualization.data  # type: ignore[union-attr]
    assert [(r["start_year"], r["trial_count"], r["estimated_count"]) for r in rows] == [  # type: ignore[index]
        ("2015", 10, 1),
        ("2016", 20, 0),
    ]
    assert [[c["nct_id"] for c in r["citations"]] for r in rows] == [["N1"], ["N2"]]  # type: ignore[index]
    assert all(r["search_url"].startswith(BASE + "/studies?") for r in rows)  # type: ignore[index]
    sizes = {r.url.params.get("pageSize") for r in transport.requests}
    assert "1000" not in sizes
    samples = [r for r in transport.requests if r.url.params.get("pageSize") == "2"]
    assert {r.url.params["sort"] for r in samples} == {"StartDate:desc"}
    assert response.meta.citations.applied == "sample"
    assert response.meta.unique_trials == 30


async def test_counted_years_answer_full_citation_requests_with_a_sample() -> None:
    client, _ = recorded_client(handler(year_2016=20))
    response = await run_plan(PLAN, client, base_url=BASE, citations_per_datum=2, citations="full")
    cited = response.meta.citations
    assert cited is not None
    assert (cited.requested, cited.applied) == ("full", "sample")
    assert cited.reason is not None and "counted per year" in cited.reason


async def test_years_that_do_not_add_up_fall_back_to_the_download() -> None:
    client, transport = recorded_client(handler(year_2016=19))
    response = await run_plan(PLAN, client, base_url=BASE, citations_per_datum=2)
    assert any(r.url.params.get("pageSize") == "1000" for r in transport.requests)
    assert response.status == "ok"
