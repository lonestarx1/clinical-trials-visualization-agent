"""GET /v1/options: the registry, so a frontend can build pickers (design Q12, Q19)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")


def test_options_list_the_registry_with_labels() -> None:
    body = TestClient(create_app()).get("/v1/options").json()
    phase = next(d for d in body["dimensions"] if d["key"] == "phase")
    assert {"value": "PHASE3", "label": "Phase 3"} in phase["values"]
    assert {m["key"] for m in body["measures"]} == {
        "trial_count",
        "total_enrollment",
        "median_enrollment",
    }
    assert {c["key"] for c in body["chart_types"]} >= {"bar_chart", "network_graph", "scatter_plot"}
    assert {"value": "RECRUITING", "label": "Recruiting"} in body["filters"]["status"]
    assert "United States" in body["filters"]["country"]
