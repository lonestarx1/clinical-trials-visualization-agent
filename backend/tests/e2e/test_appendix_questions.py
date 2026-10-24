"""Acceptance tests: the assignment's appendix questions (PA-1..PA-9), with real entities.

Run against a running stack: `make up`, then `make test-e2e` (E2E_BASE_URL, default
http://localhost:8000). Uses the real ClinicalTrials.gov API and the real models.
"""

import os
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.e2e

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000")


@dataclass(frozen=True)
class Case:
    id: str
    query: str
    chart_type: str
    dimension: str
    dimension_2: str | None = None
    groups: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


CASES = [
    Case(
        "PA-1",
        "How has the number of trials for pembrolizumab changed per year since 2015?",
        "time_series",
        "start_year",
    ),
    Case(
        "PA-2",
        "How many trials started each year for Alzheimer's disease?",
        "time_series",
        "start_year",
    ),
    Case("PA-3", "How are breast cancer trials distributed across phases?", "bar_chart", "phase"),
    Case(
        "PA-4",
        "What are the most common intervention types for melanoma trials?",
        "bar_chart",
        "intervention_type",
    ),
    Case(
        "PA-5",
        "Compare phases for trials involving pembrolizumab vs nivolumab.",
        "grouped_bar_chart",
        "phase",
        groups=2,
    ),
    Case(
        "PA-6",
        "Compare sponsor categories across breast cancer and lung cancer.",
        "grouped_bar_chart",
        "sponsor_class",
        groups=2,
    ),
    Case(
        "PA-7",
        "Which countries have the most recruiting trials for lung cancer?",
        "bar_chart",
        "country",
    ),
    Case(
        "PA-8",
        "Show a network of sponsors and drugs for multiple myeloma trials.",
        "network_graph",
        "sponsor",
        dimension_2="drug",
    ),
    Case(
        "PA-9",
        "Which drugs frequently co-occur in combination studies for melanoma?",
        "network_graph",
        "drug",
    ),
]


def data_points(visualization: dict[str, Any]) -> list[dict[str, Any]]:
    data = visualization["data"]
    if visualization["type"] == "network_graph":
        return [*data["nodes"], *data["edges"]]
    return list(data)


PARAMS = [pytest.param(c, id=c.id) for c in CASES]


@pytest.mark.parametrize("case", PARAMS)
def test_appendix_question(case: Case) -> None:
    response = httpx.post(f"{BASE_URL}/v1/query", json={"query": case.query}, timeout=300)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["schema_version"] == "2.0"
    assert body["status"] == "ok"
    viz, meta = body["visualization"], body["meta"]
    assert viz["type"] == case.chart_type
    assert viz["title"] and "summary" not in viz

    interpretation = meta["interpretation"]
    assert interpretation["dimension"] == case.dimension
    if case.dimension_2:
        assert interpretation["dimension_2"] == case.dimension_2
    assert len(meta["api_queries"]) == max(case.groups, 1)

    points = data_points(viz)
    assert points, "chart has no data"
    assert any(p["citation_count"] for p in points), "no data point has trials"
    for point in points:
        if not point["citation_count"]:
            continue  # zero-filled buckets have nothing to cite
        assert point["citations"], f"data point without citations: {point}"
        for citation in point["citations"]:
            assert citation["nct_id"].startswith("NCT")
            assert citation["evidence"]
