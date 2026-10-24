"""Fast mode (design Q22): the API picks the trials, the mirror supplies them, checked against a
live count, and live answers whenever a check fails. Run with: make test-db."""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import create_app
from app.mirror.sync import sync
from app.pipeline.query import StageLLMs
from app.store import mirror
from app.store import terms as term_store
from tests.support.fake_llm import ScriptedLLM, calls, text
from tests.support.fake_registry import FakeRegistry, registry_client

pytestmark = pytest.mark.db
Sessions = async_sessionmaker[AsyncSession]
D1, D2 = "2026-10-23T09:00:04", "2026-10-24T09:00:01"
MELANOMA = 'query.cond|"melanoma"'
PLAN = {
    "scope": "in_scope",
    "intent": "distribution",
    "chart_type": "bar_chart",
    "filters": {"conditions": ["melanoma"]},
    "dimension": "phase",
}


def study(nct: str, phases: list[str], start: str = "2018-05") -> dict[str, Any]:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": f"Trial {nct}"},
            "statusModule": {
                "overallStatus": "COMPLETED",
                "startDateStruct": {"date": start, "type": "ACTUAL"},
                "lastUpdatePostDateStruct": {"date": "2026-10-01"},
            },
            "designModule": {"studyType": "INTERVENTIONAL", "phases": phases},
        }
    }


TRIALS = [
    study("NCT1", ["PHASE2"]),
    study("NCT2", ["PHASE2", "PHASE3"]),
    study("NCT3", ["PHASE1"]),
    study("NCT4", ["PHASE3"]),
    study("NCT5", ["PHASE2"]),  # not melanoma
]


class Models:
    def factory(self, usage: Any) -> StageLLMs:
        return StageLLMs(
            ScriptedLLM(text({"verdict": "ok", "reason": ""}), stage="guard"),
            ScriptedLLM(calls(("submit_plan", {"plan": PLAN})), stage="planner"),
            ScriptedLLM(text({"title": "Melanoma trials by phase"}), stage="narrator"),
        )


@pytest.fixture
def fake() -> FakeRegistry:
    registry = FakeRegistry(TRIALS, D1)
    registry.terms[MELANOMA] = {"NCT1", "NCT2", "NCT3", "NCT4"}
    return registry


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, sessions: Sessions, fake: FakeRegistry
) -> Iterator[TestClient]:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("DATABASE_URL", os.environ["DATABASE_URL"])
    monkeypatch.setenv("FAST_MODE_ENABLED", "true")
    monkeypatch.setenv("FAST_MODE_SHADOW_RATE", "0")
    app = create_app()
    with TestClient(app) as c:
        app.state.ctgov, _ = registry_client(fake)
        app.state.llm_factory = Models().factory
        c.portal.call(sync, app.state.ctgov, app.state.sessions)  # the mirror is current at D1
        yield c


def ask(c: TestClient, **body: Any) -> dict[str, Any]:
    response = c.post("/v1/query", json={"query": "melanoma trials by phase", **body})
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def values(body: dict[str, Any]) -> dict[str, int]:
    return {d["key"]: d["trial_count"] for d in body["visualization"]["data"]}


LIVE = {"PHASE1": 1, "PHASE2": 1, "PHASE2/PHASE3": 1, "PHASE3": 1}  # melanoma: NCT1-4


def test_fast_answers_from_the_mirror_with_the_live_answer(client: TestClient) -> None:
    fast = ask(client, mode="fast")
    assert fast["meta"]["data_source"] == "fast"
    # 2 sample citations per bar, not 1: a different stored answer, so live really runs again
    live = ask(client, mode="live", citations_per_datum=2)
    assert live["meta"]["data_source"] == "live"
    assert values(fast) == values(live) == LIVE
    # Every number stays checkable against ClinicalTrials.gov: the live search URL is kept.
    assert fast["meta"]["api_queries"] == [
        q | {"total_count": 4} for q in fast["meta"]["api_queries"]
    ]
    assert "query.cond" in fast["meta"]["api_queries"][0]["url"]
    assert all(c["nct_id"] != "NCT5" for d in fast["visualization"]["data"] for c in d["citations"])


def test_a_live_request_never_gets_a_stored_fast_answer(client: TestClient) -> None:
    """Each mode has its own stored answers: asking live after fast computes live."""
    assert ask(client, mode="fast")["meta"]["data_source"] == "fast"
    live = ask(client, mode="live")
    assert live["meta"]["data_source"] == "live"
    assert live["meta"]["cache"]["result"] == "miss"
    again = ask(client, mode="fast")
    assert (again["meta"]["data_source"], again["meta"]["cache"]["result"]) == ("fast", "hit")


def test_live_is_the_default_and_unchanged(client: TestClient) -> None:
    body = ask(client)
    assert body["meta"]["data_source"] == "live"
    assert not any("Fast mode" in n for n in body["meta"]["notes"])


def test_a_mirror_behind_the_api_answers_live(client: TestClient, fake: FakeRegistry) -> None:
    fake.data_timestamp = D2  # a new update the mirror hasn't synced
    body = ask(client, mode="fast")
    assert body["meta"]["data_source"] == "live"
    assert any("syncing" in n for n in body["meta"]["notes"])
    assert values(body) == LIVE


def test_fast_mode_turned_off_answers_live(client: TestClient) -> None:
    client.app.state.settings.fast_mode_enabled = False  # type: ignore[attr-defined]
    body = ask(client, mode="fast")
    assert body["meta"]["data_source"] == "live"
    assert any("turned off" in n for n in body["meta"]["notes"])


def test_a_count_that_disagrees_answers_live(client: TestClient) -> None:
    sessions: Sessions = client.app.state.sessions  # type: ignore[attr-defined]

    async def drift() -> None:  # the mirror and its term set hold a trial the API doesn't
        now = datetime.now(UTC)
        async with sessions() as s:
            await mirror.upsert_trials(s, [study("NCT9", ["PHASE1"])])
            await term_store.save(
                s,
                term_key=MELANOMA,
                param="query.cond",
                expression='"melanoma"',
                ids={"NCT1", "NCT2", "NCT3", "NCT4", "NCT9"},
                old=set(),
                data_timestamp=D1,
                checked_at=now,
                resolved_at=now,
            )
            await s.commit()

    client.portal.call(drift)
    body = ask(client, mode="fast")
    assert body["meta"]["data_source"] == "live"
    assert any("disagreed" in n for n in body["meta"]["notes"])
    assert values(body) == LIVE  # the live answer


def test_a_large_new_term_answers_live(client: TestClient) -> None:
    client.app.state.settings.fast_new_term_max_trials = 3  # type: ignore[attr-defined]
    body = ask(client, mode="fast")
    assert body["meta"]["data_source"] == "live"
    assert any("not prepared yet" in n for n in body["meta"]["notes"])


def test_health_reports_whether_fast_mode_is_ready(client: TestClient, fake: FakeRegistry) -> None:
    assert client.get("/health").json()["fast_mode"] == {"status": "ready", "data_timestamp": D1}
    fake.data_timestamp = D2
    assert client.get("/health").json()["fast_mode"]["status"] == "syncing"
