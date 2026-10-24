"""GET /health (design Q12): liveness plus a database check."""

import pytest
from fastapi.testclient import TestClient

from app.api.health import get_database_check
from app.main import create_app


def client_with_database(ok: bool) -> TestClient:
    app = create_app()

    async def fake_check() -> bool:
        return ok

    app.dependency_overrides[get_database_check] = lambda: fake_check
    return TestClient(app)


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")


def test_health_ok_when_database_is_reachable() -> None:
    response = client_with_database(ok=True).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}


def test_health_unavailable_when_database_is_down() -> None:
    response = client_with_database(ok=False).get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "checks": {"database": "error"}}


def test_health_is_in_the_openapi_document() -> None:
    paths = client_with_database(ok=True).get("/openapi.json").json()["paths"]
    assert "/health" in paths
