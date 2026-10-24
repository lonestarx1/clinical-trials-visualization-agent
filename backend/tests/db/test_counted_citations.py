"""Trials-per-year answers counted per year: the citations endpoint lists every trial (Q6, Q14).

The answer reads only a sample of each year; the rest of a year's trials are paged from
ClinicalTrials.gov when a client asks for them. Run with: make test-db.
"""

import os
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.pipeline.query import StageLLMs
from tests.support.fake_llm import ScriptedLLM, calls, text
from tests.support.fakes import json_response
from tests.support.recorded_api import VERSION, recorded_client

pytestmark = pytest.mark.db

Y15 = "AREA[StartDate]RANGE[2015-01-01,2015-12-31]"
Y16 = "AREA[StartDate]RANGE[2016-01-01,2016-12-31]"
SPAN = "AREA[StartDate]RANGE[2015-01-01,2016-12-31]"
EST = "AREA[StartDateType]ESTIMATED"
TREND = {
    "scope": "in_scope",
    "intent": "trend",
    "chart_type": "time_series",
    "dimension": "start_year",
    "filters": {"start_year_min": 2015, "start_year_max": 2016},
}


def study(nct: str, date: str) -> dict[str, Any]:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": f"Trial {nct}"},
            "statusModule": {"startDateStruct": {"date": date, "type": "ACTUAL"}},
        }
    }


# 2015 as the API lists it, newest first, two pages. NCT00000004's start date has moved to 2014
# since the count: it no longer belongs to 2015 and isn't cited.
PAGE_1 = [
    study("NCT00000001", "2015-12-31"),
    study("NCT00000002", "2015-10-01"),
    study("NCT00000003", "2015-06-15"),
]
PAGE_2 = [study("NCT00000004", "2014-05-01"), study("NCT00000005", "2015-01-02")]
COUNTS = {
    SPAN: 30_000,
    f"({SPAN} AND {SPAN})": 30_000,
    f"({SPAN} AND {Y15})": 10_000,
    f"({SPAN} AND {Y16})": 20_000,
    f"(({SPAN} AND {Y15}) AND {EST})": 1_000,
    f"(({SPAN} AND {Y16}) AND {EST})": 0,
}


def respond(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    if request.url.path.endswith("/version"):
        return json_response(VERSION)
    advanced = params.get("filter.advanced", "")
    if params.get("countTotal") == "true" and params["pageSize"] == "1":
        return json_response({"studies": [], "totalCount": COUNTS[advanced]})
    if Y16 in advanced:
        return json_response({"studies": [study("NCT00000006", "2016-11-02")]})
    if params["pageSize"] == "1":  # the answer's own sample of 2015
        return json_response({"studies": PAGE_1[:1]})
    assert params["sort"] == "StartDate:desc"
    if params.get("pageToken") == "t2":
        return json_response({"studies": PAGE_2})
    return json_response({"studies": PAGE_1, "nextPageToken": "t2"})


def factory(usage: Any) -> StageLLMs:
    return StageLLMs(
        ScriptedLLM(text({"verdict": "ok", "reason": ""}), stage="guard"),
        ScriptedLLM(calls(("submit_plan", {"plan": TREND})), stage="planner"),
        ScriptedLLM(text({"title": "Trials started per year"}), stage="narrator"),
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, sessions: Any) -> Iterator[TestClient]:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("DATABASE_URL", os.environ["DATABASE_URL"])
    app = create_app()
    with TestClient(app) as c:
        app.state.ctgov, _ = recorded_client(respond)
        app.state.llm_factory = factory
        yield c


def citations(c: TestClient, result_id: str, **params: Any) -> dict[str, Any]:
    response = c.get(f"/v1/results/{result_id}/citations", params={"datum": "2015", **params})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_every_trial_of_a_counted_year_is_listed(client: TestClient) -> None:
    body = client.post(
        "/v1/query",
        json={"query": "How many trials started each year in 2015-2016?", "citations_per_datum": 1},
    ).json()
    row = next(r for r in body["visualization"]["data"] if r["key"] == "2015")
    assert (row["trial_count"], row["citation_count"], len(row["citations"])) == (10_000, 10_000, 1)

    first = citations(client, body["result_id"], page_size=2)
    assert first["citation_count"] == 10_000
    assert [x["nct_id"] for x in first["citations"]] == ["NCT00000001", "NCT00000002"]
    assert first["next_cursor"] == 2
    rest = citations(client, body["result_id"], page_size=10, cursor=first["next_cursor"])
    assert [x["nct_id"] for x in rest["citations"]] == ["NCT00000003", "NCT00000005"]
    assert rest["next_cursor"] is None
    assert rest["citations"][1]["evidence"] == [
        {"field": "protocolSection.statusModule.startDateStruct.date", "excerpt": "2015-01-02"}
    ]


def test_listing_a_counted_year_again_reads_what_was_stored(client: TestClient) -> None:
    body = client.post(
        "/v1/query",
        json={"query": "How many trials started each year in 2015-2016?", "citations_per_datum": 1},
    ).json()
    once = citations(client, body["result_id"], page_size=10)
    ctgov, transport = recorded_client(respond)
    client.app.state.ctgov = ctgov  # type: ignore[attr-defined]
    again = citations(client, body["result_id"], page_size=10)
    assert again["citations"] == once["citations"]
    assert transport.requests == []
