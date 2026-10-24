"""The gate turns back a question that names nothing to filter or group by ("Show me trials"):
answered, it would read the whole registry, minutes of work for a chart nobody asked for."""

from typing import Any

import pytest

from app.schemas.request import QueryRequest
from app.validation.gate import check_plan

BY_PHASE: dict[str, Any] = {
    "scope": "in_scope",
    "intent": "distribution",
    "chart_type": "bar_chart",
    "dimension": "phase",
}
TOTAL: dict[str, Any] = {"scope": "in_scope", "intent": "single_number", "chart_type": "metric"}


def gate(query: str, plan: dict[str, Any]):  # type: ignore[no-untyped-def]
    return check_plan(plan, QueryRequest(query=query), final=True)


@pytest.mark.parametrize("query", ["Show me trials", "clinical trials", "give me some data"])
@pytest.mark.parametrize("plan", [BY_PHASE, TOTAL], ids=["chart", "metric"])
def test_a_question_naming_nothing_is_turned_back(query: str, plan: dict[str, Any]) -> None:
    result = gate(query, plan)
    assert result.plan is None
    assert any("too broad" in e and "scope_suggestion" in e for e in result.errors)


@pytest.mark.parametrize(
    ("query", "plan"),
    [
        ("How are trials distributed across phases?", BY_PHASE),  # the grouping is named
        ("trials by phase", BY_PHASE),
        ("Which phase has the most trials?", BY_PHASE),
        ("How many trials are there in total on ClinicalTrials.gov?", TOTAL),  # a count, cheap
        ("Show me trials", BY_PHASE | {"filters": {"conditions": ["trials"]}}),  # a filter
    ],
)
def test_a_named_grouping_filter_or_count_passes(query: str, plan: dict[str, Any]) -> None:
    assert not any("too broad" in e for e in gate(query, plan).errors)


def test_request_fields_count_as_named() -> None:
    request = QueryRequest(query="Show me trials", trial_phase=["PHASE3"])
    result = check_plan(BY_PHASE, request, final=True)
    assert not any("too broad" in e for e in result.errors)


def test_out_of_scope_plans_pass() -> None:
    plan = BY_PHASE | {"scope": "out_of_scope", "scope_reason": "too broad"}
    assert gate("Show me trials", plan).errors == []
