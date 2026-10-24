"""Routing errors use the single error body too (design Q17), not the framework's default."""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_ctgov, get_llm_factory
from app.main import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    app = create_app()
    app.dependency_overrides[get_ctgov] = lambda: None
    app.dependency_overrides[get_llm_factory] = lambda: None
    return TestClient(app)


def _error(response: object) -> dict[str, object]:
    body = response.json()  # type: ignore[attr-defined]
    assert set(body) == {"error"}, body
    error: dict[str, object] = body["error"]
    assert set(error) == {"code", "message", "details", "trace_id"}
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["trace_id"], str) and error["trace_id"]
    return error


def test_unknown_path_is_not_found(client: TestClient) -> None:
    response = client.get("/v1/no-such-path")
    assert response.status_code == 404
    assert _error(response)["code"] == "not_found"


def test_wrong_method_is_method_not_allowed(client: TestClient) -> None:
    response = client.get("/v1/query")
    assert response.status_code == 405
    assert _error(response)["code"] == "method_not_allowed"
    assert response.headers["allow"] == "POST"


def test_validation_errors_keep_their_details(client: TestClient) -> None:
    response = client.post("/v1/query", json={"query": "x", "colour": "red"})
    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "invalid_request"
    assert error["details"] == [
        {"loc": ["body", "colour"], "msg": "Extra inputs are not permitted"}
    ]


def test_usage_without_the_admin_token_is_unauthorized(client: TestClient) -> None:
    response = client.get("/v1/usage")
    assert response.status_code == 401
    assert _error(response)["code"] == "unauthorized"


def test_cancelling_a_job_without_a_database_is_not_found(client: TestClient) -> None:
    response = client.delete("/v1/jobs/8c1f6c52-4a8e-4d3b-9a51-0f2e7b6d9c11")
    assert response.status_code == 404
    assert _error(response)["code"] == "not_found"


def test_browsers_may_send_delete_across_origins(client: TestClient) -> None:
    """The CORS preflight for DELETE /v1/jobs/{id} (a client calling the API directly)."""
    response = client.options(
        "/v1/jobs/8c1f6c52-4a8e-4d3b-9a51-0f2e7b6d9c11",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "DELETE"},
    )
    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]
