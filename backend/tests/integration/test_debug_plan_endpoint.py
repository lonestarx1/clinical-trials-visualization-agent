"""POST /v1/debug/plan: a hand-written plan through the whole non-AI pipeline (M1b exit check).

The API is faked with the recorded studies; expected values are the hand-computed
ones from tests/unit/test_charts.py.
"""

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_ctgov
from app.main import create_app
from app.schemas.response import QueryResponse
from tests.support.recorded_api import recorded_client, recorded_handler

PA3 = {
    "scope": "in_scope",
    "intent": "distribution",
    "chart_type": "bar_chart",
    "filters": {"conditions": ["breast cancer"]},
    "dimension": "phase",
}


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")


def app_with(handler: Any = None) -> TestClient:
    app = create_app()
    client, _ = recorded_client(handler)
    app.dependency_overrides[get_ctgov] = lambda: client
    return TestClient(app)


def post(body: dict[str, Any], handler: Any = None) -> httpx.Response:
    return app_with(handler).post("/v1/debug/plan", json=body)


def test_plan_runs_end_to_end() -> None:
    response = post({"plan": PA3})
    assert response.status_code == 200, response.text
    body = QueryResponse.model_validate(response.json())

    assert (body.schema_version, body.status) == ("2.0", "ok")
    assert body.visualization is not None
    assert body.visualization.type == "bar_chart"
    assert [(r["phase"], r["trial_count"]) for r in body.visualization.data] == [
        ("Phase 1", 1),
        ("Phase 1/Phase 2", 1),
        ("Phase 2", 2),
        ("Phase 3", 1),
        ("Not Applicable", 1),
        ("No phase (observational / expanded access)", 2),
    ]
    meta = body.meta
    assert meta.interpretation is not None and meta.interpretation.dimension == "phase"
    assert [q.model_dump() for q in meta.api_queries] == [
        {
            "group": None,
            "url": "https://clinicaltrials.gov/api/v2/studies?query.cond=%22breast+cancer%22",
            "total_count": 8,
        }
    ]
    assert meta.data_timestamp == "2026-10-23T09:00:04"
    assert meta.unique_trials == 8 and meta.additive is True
    assert meta.filters == {"conditions": ["breast cancer"]}
    assert meta.citations is not None and meta.citations.per_datum == 5
    assert meta.trace_id and meta.retrieved_at


def test_citations_per_datum_is_applied() -> None:
    body = post({"plan": PA3, "citations_per_datum": 1}).json()
    assert all(len(row["citations"]) <= 1 for row in body["visualization"]["data"])


def test_comparison_records_one_query_per_group() -> None:
    plan = PA3 | {
        "intent": "comparison",
        "chart_type": "grouped_bar_chart",
        "filters": {},
        "groups": [
            {"label": "Pembrolizumab", "filters": {"drugs": ["pembrolizumab"]}},
            {"label": "Nivolumab", "filters": {"drugs": ["nivolumab"]}},
        ],
    }
    body = post({"plan": plan}).json()
    assert body["visualization"]["type"] == "grouped_bar_chart"
    assert [q["group"] for q in body["meta"]["api_queries"]] == ["Pembrolizumab", "Nivolumab"]
    assert body["meta"]["group_overlap"] == [
        {"groups": ["Pembrolizumab", "Nivolumab"], "trials": 8}
    ]


def test_no_matching_trials_is_a_200_without_a_chart() -> None:
    body = post({"plan": PA3}, recorded_handler(lambda _: False)).json()
    assert body["status"] == "no_matching_trials"
    assert body["visualization"] is None
    assert body["meta"]["details"] == {"search_counts": [{"group": None, "count": 0}]}


def test_year_filter_note() -> None:
    plan = PA3 | {"filters": {"conditions": ["breast cancer"], "start_year_min": 2015}}
    notes = post({"plan": plan}).json()["meta"]["notes"]
    assert "The year filter excludes trials without a start date." in notes


def test_upstream_failure_uses_the_error_body() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    response = post({"plan": PA3}, down)
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "upstream_unavailable"
    assert error["trace_id"]
    assert "Traceback" not in response.text


def test_invalid_plans_get_a_422_with_field_errors() -> None:
    response = post({"plan": PA3 | {"dimension": "favourite_colour"}})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert any("dimension" in item["loc"] for item in error["details"])


def test_mostly_estimated_years_are_flagged() -> None:
    """Design Q10, D10.8. In the recorded data, 2026 has one trial with an estimated start."""
    plan = PA3 | {"intent": "trend", "chart_type": "time_series", "dimension": "start_year"}
    warnings = post({"plan": plan}).json()["meta"]["warnings"]
    assert warnings == ["Most trials in 2026 have estimated (planned) dates."]


def test_network_plans_run_end_to_end() -> None:
    plan = PA3 | {"intent": "network", "chart_type": "network_graph", "dimension": "drug"}
    body = post({"plan": plan}).json()
    assert body["visualization"]["type"] == "network_graph"
    assert body["meta"]["network"]["edges"] == 29
    assert body["meta"]["warnings"] == []
