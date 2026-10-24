"""The gate stops a plan from quietly counting something other than what the question asks."""

from typing import Any

import pytest

from app.schemas.request import QueryRequest
from app.validation.gate import check_plan

SCREENSHOT = "rank years 2010-2020 on the number of sponsors sponsoring over 2 trials"
YEARS = {"start_year_min": 2010, "start_year_max": 2020}
TREND: dict[str, Any] = {
    "scope": "in_scope",
    "intent": "trend",
    "chart_type": "time_series",
    "dimension": "start_year",
    "filters": YEARS,
}
SPONSORS_3 = {"measure": "distinct_count", "options": {"count_entity": "sponsor", "min_trials": 3}}


def gate(query: str, plan: dict[str, Any]):  # type: ignore[no-untyped-def]
    return check_plan(plan, QueryRequest(query=query), final=True)


def test_counting_trials_when_the_question_counts_sponsors_is_rejected() -> None:
    plan = TREND | {"assumptions": ["count of sponsors with more than 2 trials per year"]}
    result = gate(SCREENSHOT, plan)
    assert result.plan is None
    assert any("distinct_count" in e and "count_entity=sponsor" in e for e in result.errors)


def test_counting_sponsors_with_a_threshold_passes() -> None:
    result = gate(SCREENSHOT, TREND | SPONSORS_3)
    assert result.errors == [] and result.plan is not None


@pytest.mark.parametrize(
    ("query", "entity"),
    [
        ("How many drugs were tested each year in breast cancer since 2010?", "drug"),
        ("count of unique countries per year since 2010", "country"),
        ("number of distinct lead sponsors per year since 2010", "sponsor"),
    ],
)
def test_each_entity_word_needs_its_own_count(query: str, entity: str) -> None:
    result = gate(query, TREND)
    assert any(f"count_entity={entity}" in e for e in result.errors)


@pytest.mark.parametrize(
    "query",
    [
        "number of trials by sponsor",
        "Which sponsors run the most lung cancer trials?",
        "How many trials did each sponsor run?",
    ],
)
def test_trials_per_sponsor_is_not_a_sponsor_count(query: str) -> None:
    plan = {
        "scope": "in_scope",
        "intent": "top_n",
        "chart_type": "bar_chart",
        "dimension": "sponsor",
    }
    result = gate(query, plan)
    assert result.errors == []


@pytest.mark.parametrize(
    ("dimension", "dimension_2"), [("enrollment", "site_count"), ("site_count", "enrollment")]
)
def test_the_number_of_sites_per_trial_is_not_a_site_count(
    dimension: str, dimension_2: str
) -> None:
    """Found by the AI eval (B-04): a scatter of enrollment against each trial's number of
    sites was rejected three times, and the planner gave up with a refusal."""
    plan = {
        "scope": "in_scope",
        "intent": "numeric_relationship",
        "chart_type": "scatter_plot",
        "filters": {"conditions": ["COVID-19"], "phases": ["PHASE3"]},
        "dimension": dimension,
        "dimension_2": dimension_2,
    }
    query = "Is there a relationship between enrollment and the number of sites in phase 3 COVID-19 trials?"
    assert gate(query, plan).errors == []


def test_out_of_scope_plans_are_not_checked_for_the_measure() -> None:
    plan = TREND | {"scope": "out_of_scope", "scope_reason": "no such measure"}
    assert gate(SCREENSHOT, plan).errors == []


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"chart_type": "histogram", "dimension": "enrollment"}, "distinct_count can't"),
        ({"chart_type": "network_graph", "dimension": "drug"}, "distinct_count can't"),
        (
            {"chart_type": "bar_chart", "dimension": "sponsor", "intent": "top_n"},
            "count_entity must differ from the dimension",
        ),
    ],
)
def test_distinct_count_fits_only_some_charts(changes: dict[str, Any], message: str) -> None:
    result = gate("number of sponsors with over 2 trials", TREND | SPONSORS_3 | changes)
    assert any(message in e for e in result.errors)
