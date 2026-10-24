"""GET /health (design Q12): liveness plus a database check."""

import pytest
from fastapi.testclient import TestClient

from app.api.health import get_data_version, get_database_check
from app.ctgov.client import CtgovUnavailable, VersionInfo
from app.main import create_app

VERSION = VersionInfo(api_version="2.0.5", data_timestamp="2026-10-23T09:00:04")


def client_with_database(ok: bool, ctgov_ok: bool = True) -> TestClient:
    app = create_app()

    async def fake_check() -> bool:
        return ok

    async def fake_version() -> VersionInfo:
        if not ctgov_ok:
            raise CtgovUnavailable("down")
        return VERSION

    app.dependency_overrides[get_database_check] = lambda: fake_check
    app.dependency_overrides[get_data_version] = lambda: fake_version
    return TestClient(app)


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")


def test_health_ok_when_database_is_reachable() -> None:
    response = client_with_database(ok=True).get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "ctgov": "ok"},
        "data_timestamp": "2026-10-23T09:00:04",
        "fast_mode": {"status": "off", "data_timestamp": None},  # off by default
    }


def test_health_unavailable_when_database_is_down() -> None:
    response = client_with_database(ok=False).get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["checks"]["database"] == "error"


def test_clinicaltrials_outage_is_reported_but_not_fatal() -> None:
    """The container stays healthy; queries fail with their own errors (Q17)."""
    response = client_with_database(ok=True, ctgov_ok=False).get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "ctgov": "error"},
        "data_timestamp": None,
        "fast_mode": {"status": "off", "data_timestamp": None},
    }


def test_health_is_in_the_openapi_document() -> None:
    paths = client_with_database(ok=True).get("/openapi.json").json()["paths"]
    assert "/health" in paths
