"""Acceptance: questions that count entities, and measures we can't compute. Opt-in: -m e2e."""

import os

import httpx
import pytest

pytestmark = pytest.mark.e2e

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000")


def ask(query: str) -> dict:  # type: ignore[type-arg]
    response = httpx.post(f"{BASE_URL}/v1/query", json={"query": query}, timeout=300)
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def test_counting_sponsors_with_a_threshold_uses_distinct_count() -> None:
    body = ask("How many sponsors ran more than 2 pembrolizumab trials each year since 2018?")
    assert body["status"] == "ok"
    assert body["meta"]["interpretation"]["measure"] == "distinct_count"
    y = body["visualization"]["encoding"]["y"]
    assert y["label"] == "Lead sponsors with at least 3 trials"


def test_an_average_duration_is_refused_with_a_suggestion() -> None:
    body = ask("What is the average trial duration per year for breast cancer since 2015?")
    assert body["status"] == "out_of_scope"
    assert body["meta"]["details"]["reason"]
    assert body["meta"]["details"].get("suggestion")
