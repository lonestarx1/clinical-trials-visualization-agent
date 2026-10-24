"""Plan gate (design Q3, Q4b V1/V2/V4, Q5 merge rules): code re-checks every submitted plan."""

from typing import Any

import pytest

from app.schemas.request import QueryRequest
from app.validation.gate import check_plan, default_chart

BASE: dict[str, Any] = {
    "scope": "in_scope",
    "intent": "distribution",
    "chart_type": "bar_chart",
    "filters": {"conditions": ["breast cancer"]},
    "dimension": "phase",
}


def req(
    query: str = "How are breast cancer trials distributed across phases?", **f: Any
) -> QueryRequest:
    return QueryRequest.model_validate({"query": query} | f)


def gate(plan: dict[str, Any], request: QueryRequest | None = None, final: bool = False):  # type: ignore[no-untyped-def]
    return check_plan(plan, request or req(), final=final)


def test_a_good_plan_passes() -> None:
    result = gate(BASE)
    assert result.errors == [] and result.plan is not None


def test_schema_errors_are_reported_readably() -> None:
    result = gate(BASE | {"dimension": "colour"})
    assert result.plan is None
    assert any("dimension" in e and "unknown dimension" in e for e in result.errors)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"chart_type": "time_series"}, "time_series needs a time dimension"),
        ({"chart_type": "histogram"}, "histogram needs a numeric dimension"),
        ({"chart_type": "metric"}, "metric takes no dimension"),
        ({"chart_type": "grouped_bar_chart"}, "grouped_bar_chart needs comparison groups"),
        ({"dimension": None}, "bar_chart needs a dimension"),
        ({"dimension": "enrollment"}, "bar_chart needs a categorical or entity dimension"),
        ({"chart_type": "network_graph", "dimension": "enrollment"}, "network_graph needs entity"),
        (
            {"chart_type": "scatter_plot", "dimension": "enrollment"},
            "scatter_plot needs two numeric",
        ),
        (
            {"chart_type": "scatter_plot", "dimension": "phase", "dimension_2": "enrollment"},
            "scatter_plot needs two numeric",
        ),
    ],
)
def test_chart_compatibility(changes: dict[str, Any], message: str) -> None:
    errors = gate(BASE | changes).errors
    assert any(message in e for e in errors), errors


def test_comparisons_need_groups_or_must_not_have_them() -> None:
    groups = [
        {"label": "A", "filters": {"drugs": ["breast cancer"]}},
        {"label": "B", "filters": {"drugs": ["breast cancer"]}},
    ]
    assert any(
        "bar_chart can't show comparison groups" in e
        for e in gate(BASE | {"groups": groups}).errors
    )


def test_entities_must_come_from_the_question_or_fields() -> None:
    result = gate(BASE | {"filters": {"conditions": ["breast cancer"], "drugs": ["trastuzumab"]}})
    assert any("'trastuzumab' does not appear in the question" in e for e in result.errors)


@pytest.mark.parametrize(
    "term", ["Breast Cancer", "breast-cancer", "breast cancers", "brest cancer"]
)
def test_grounding_tolerates_case_punctuation_and_small_typos(term: str) -> None:
    assert gate(BASE | {"filters": {"conditions": [term]}}).errors == []


def test_synonyms_are_not_grounded_the_api_resolves_them() -> None:
    plan = BASE | {"filters": {"drugs": ["pembrolizumab"]}}
    errors = gate(plan, req("How many Keytruda trials per phase?")).errors
    assert any("pembrolizumab" in e for e in errors)


def test_unrequested_filters_need_an_assumption() -> None:
    plan = BASE | {"filters": {"conditions": ["breast cancer"], "statuses": ["RECRUITING"]}}
    assert any("statuses" in e and "assumptions" in e for e in gate(plan).errors)
    assert (
        gate(
            plan
            | {
                "assumptions": [
                    "Only recruiting trials, since the user asked about current trials."
                ]
            }
        ).errors
        == []
    )
    asked = req("Which recruiting breast cancer trials are in each phase?")
    assert gate(plan, asked).errors == []


def test_unrequested_years_need_an_assumption() -> None:
    plan = BASE | {"filters": {"conditions": ["breast cancer"], "start_year_min": 2015}}
    assert any("start_year_min" in e for e in gate(plan).errors)
    assert gate(plan, req("Breast cancer trials by phase since 2015")).errors == []


def test_request_fields_override_the_plan_with_a_warning() -> None:
    request = req(
        "How are these trials distributed across phases?",
        condition="lung cancer",
        trial_phase=["Phase 3"],
        start_year=2018,
        top_n=5,
        sponsor_role="any",
    )
    result = gate(BASE, request)
    assert result.plan is not None
    f = result.plan.filters
    assert (f.conditions, [p.value for p in f.phases], f.start_year_min, f.sponsor_role) == (
        ["lung cancer"],
        ["PHASE3"],
        2018,
        "any",
    )
    assert result.plan.options.top_n == 5
    assert (
        "The condition field (lung cancer) overrides the question's breast cancer."
        in result.warnings
    )


def test_compare_field_becomes_groups() -> None:
    request = req(
        "Compare phases",
        compare=[
            {"label": "Pembro", "drug_name": "pembrolizumab"},
            {"label": "Nivo", "drug_name": "nivolumab"},
        ],
    )
    plan = BASE | {"intent": "comparison", "chart_type": "grouped_bar_chart", "filters": {}}
    result = gate(plan, request)
    assert result.plan is not None
    assert [(g.label, g.filters.drugs) for g in result.plan.groups] == [
        ("Pembro", ["pembrolizumab"]),
        ("Nivo", ["nivolumab"]),
    ]


def test_chart_type_field_wins_and_is_checked() -> None:
    result = gate(BASE, req(chart_type="time_series"))
    assert any("time_series needs a time dimension" in e for e in result.errors)


def test_only_a_wrong_chart_type_falls_back_to_the_default_for_the_intent() -> None:
    result = gate(BASE | {"chart_type": "time_series"}, final=True)
    assert result.errors == []
    assert result.plan is not None and result.plan.chart_type == "bar_chart"
    assert result.chart_type_source == "fallback"


def test_out_of_scope_plans_skip_the_chart_checks() -> None:
    plan = {
        "scope": "out_of_scope",
        "scope_reason": "asks whether a drug works",
        "intent": "single_number",
        "chart_type": "metric",
    }
    assert gate(plan, req("Does pembrolizumab work?")).errors == []


def test_default_charts() -> None:
    assert default_chart("trend") == "time_series"
    assert default_chart("comparison") == "grouped_bar_chart"
    assert default_chart("single_number") == "metric"


@pytest.mark.parametrize(
    "changes",
    [
        {"intent": "network", "chart_type": "network_graph", "dimension": "drug"},
        {
            "intent": "network",
            "chart_type": "network_graph",
            "dimension": "sponsor",
            "dimension_2": "drug",
        },
        {
            "intent": "numeric_relationship",
            "chart_type": "scatter_plot",
            "dimension": "enrollment",
            "dimension_2": "duration_months",
        },
    ],
)
def test_networks_and_scatter_plots_are_accepted(changes: dict[str, Any]) -> None:
    assert gate(BASE | changes).errors == []


def test_series_splits() -> None:
    trend = BASE | {"intent": "trend", "chart_type": "time_series", "dimension": "start_year"}
    assert gate(trend | {"dimension_2": "phase"}).errors == []
    assert (
        gate(BASE | {"chart_type": "grouped_bar_chart", "dimension_2": "study_type"}).errors == []
    )
    errors = gate(trend | {"dimension_2": "enrollment"}).errors
    assert any("dimension_2" in e for e in errors)
