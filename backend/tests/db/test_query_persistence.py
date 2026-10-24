"""/v1/query with Postgres: stored results, full citations, caches, jobs, budget (Q6, Q8, Q14, Q16).

Scripted models and the recorded API; a real database. Run with: make test-db.
"""

import os
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.pipeline.query import StageLLMs
from tests.support.fake_llm import ScriptedLLM, calls, text
from tests.support.recorded_api import recorded_client, recorded_handler

pytestmark = pytest.mark.db

PA3 = {
    "scope": "in_scope",
    "intent": "distribution",
    "chart_type": "bar_chart",
    "filters": {"conditions": ["breast cancer"]},
    "dimension": "phase",
}
QUESTION = {
    "query": "How are breast cancer trials distributed across phases?",
    "citations_per_datum": 1,
}
OK = text({"verdict": "ok", "reason": ""})
NARRATION = text({"title": "Breast cancer trials by phase"})


class Models:
    """Fresh scripted models per request, recording how many planner calls were made."""

    def __init__(self) -> None:
        self.planner_calls = 0
        self.guard_calls = 0

    def factory(self, usage: Any) -> StageLLMs:
        planner = ScriptedLLM(calls(("submit_plan", {"plan": PA3})), stage="planner")
        guard = ScriptedLLM(OK, stage="guard")
        original_planner, original_guard = planner.respond, guard.respond

        async def counted_planner(*a: Any, **k: Any) -> Any:
            self.planner_calls += 1
            return await original_planner(*a, **k)

        async def counted_guard(*a: Any, **k: Any) -> Any:
            self.guard_calls += 1
            return await original_guard(*a, **k)

        planner.respond, guard.respond = counted_planner, counted_guard  # type: ignore[method-assign]
        return StageLLMs(guard, planner, ScriptedLLM(NARRATION, stage="narrator"))


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, sessions: Any) -> Iterator[tuple[TestClient, Models]]:
    """`sessions` empties the tables first, so caches never leak between tests."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("ADMIN_TOKEN", "admin-secret-for-tests")
    monkeypatch.setenv("DATABASE_URL", os.environ["DATABASE_URL"])
    app = create_app()
    models = Models()
    with TestClient(app) as c:
        app.state.ctgov, _ = recorded_client()
        app.state.llm_factory = models.factory
        yield c, models


def test_results_are_stored_and_full_citations_paged(client: tuple[TestClient, Models]) -> None:
    c, _ = client
    body = c.post("/v1/query", json=QUESTION).json()
    result_id = body["result_id"]
    assert result_id and body["status"] == "ok"
    phase2 = next(r for r in body["visualization"]["data"] if r["phase"] == "Phase 2")
    assert len(phase2["citations"]) == 1 and phase2["citation_count"] == 2

    page = c.get(
        f"/v1/results/{result_id}/citations", params={"datum": "PHASE2", "page_size": 1}
    ).json()
    assert (page["citation_count"], len(page["citations"]), page["next_cursor"]) == (2, 1, 1)
    rest = c.get(
        f"/v1/results/{result_id}/citations",
        params={"datum": "PHASE2", "cursor": 1, "page_size": 1},
    ).json()
    assert [x["nct_id"] for x in rest["citations"]] == ["NCT02648477"] and rest[
        "next_cursor"
    ] is None


def test_citations_errors(client: tuple[TestClient, Models]) -> None:
    c, _ = client
    missing = c.get(
        "/v1/results/00000000-0000-4000-8000-000000000000/citations", params={"datum": "X"}
    )
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


def test_repeat_questions_reuse_the_plan_and_the_result(client: tuple[TestClient, Models]) -> None:
    c, models = client
    first = c.post("/v1/query", json=QUESTION).json()
    second = c.post("/v1/query", json=QUESTION).json()
    assert models.planner_calls == 1  # the plan came from the cache the second time
    assert models.guard_calls == 2  # the guard always runs
    assert second["meta"]["cache"] == {"plan": "hit", "result": "hit"}
    assert second["result_id"] == first["result_id"]
    assert second["visualization"] == first["visualization"]


def test_broad_questions_become_background_jobs(
    client: tuple[TestClient, Models], monkeypatch: pytest.MonkeyPatch
) -> None:
    c, _ = client
    app = c.app
    app.state.settings.sync_max_seconds = 1  # 8 trials = 1 page, estimated above 1 s
    response = c.post("/v1/query", json=QUESTION)
    assert response.status_code == 202
    accepted = response.json()
    assert (
        accepted["status"] == "pending" and accepted["poll_url"] == f"/v1/jobs/{accepted['job_id']}"
    )

    deadline = time.time() + 15
    job: dict[str, Any] = {}
    while time.time() < deadline:
        job = c.get(accepted["poll_url"]).json()
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.2)
    assert job["status"] == "succeeded", job
    assert job["result"]["visualization"]["type"] == "bar_chart"
    assert job["result"]["result_id"]


def test_daily_budget_is_enforced(client: tuple[TestClient, Models]) -> None:
    c, _ = client
    c.app.state.settings.llm_daily_budget_usd = 0.0000001
    c.post("/v1/query", json=QUESTION)  # spends a little (recorded usage)
    blocked = c.post("/v1/query", json=QUESTION | {"query": "Breast cancer trials by phase please"})
    assert blocked.status_code == 503
    assert blocked.json()["error"]["code"] == "budget_exceeded"


def test_usage_needs_the_admin_token(client: tuple[TestClient, Models]) -> None:
    c, _ = client
    c.post("/v1/query", json=QUESTION)
    assert c.get("/v1/usage").status_code == 401
    usage = c.get("/v1/usage", headers={"Authorization": "Bearer admin-secret-for-tests"}).json()
    assert usage["calls"] >= 3 and usage["budget_usd"] == 100


def test_zero_counts_still_answer_without_a_job(client: tuple[TestClient, Models]) -> None:
    c, _ = client
    c.app.state.ctgov, _ = recorded_client(recorded_handler(lambda _: False))
    body = c.post("/v1/query", json=QUESTION).json()
    assert body["status"] == "no_matching_trials"
