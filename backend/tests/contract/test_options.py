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
        "distinct_count",
    }
    assert {c["key"] for c in body["chart_types"]} >= {"bar_chart", "network_graph", "scatter_plot"}
    assert {"value": "RECRUITING", "label": "Recruiting"} in body["filters"]["status"]
    assert "United States" in body["filters"]["country"]


def test_per_client_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Design Q19: RATE_LIMIT_PER_IP_PER_MIN, 429 too_many_requests with Retry-After."""
    monkeypatch.setenv("RATE_LIMIT_PER_IP_PER_MIN", "2")
    client = TestClient(create_app())
    assert [client.get("/v1/options").status_code for _ in range(2)] == [200, 200]
    limited = client.get("/v1/options")
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "too_many_requests"
    assert int(limited.headers["Retry-After"]) >= 1
    assert client.get("/health").status_code != 429  # health checks are never limited
