"""Request (design Q5) and QueryPlan (design Q4a) schemas."""

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.plan import QueryPlan
from app.schemas.request import QueryRequest

NEXT_YEAR_LIMIT = date.today().year + 10


def plan(**overrides: Any) -> QueryPlan:
    base: dict[str, Any] = {
        "scope": "in_scope",
        "intent": "distribution",
        "chart_type": "bar_chart",
        "filters": {"conditions": ["breast cancer"]},
        "dimension": "phase",
        "measure": "trial_count",
    }
    return QueryPlan.model_validate(base | overrides)


# ---------- QueryPlan ----------


def test_minimal_plan_has_design_defaults() -> None:
    p = plan()
    assert p.groups == []
    assert p.filters.sponsor_role == "lead"
    assert p.filters.match_mode == "strict"
    assert p.dimension_2 is None
    assert p.assumptions == []


def test_plan_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        plan(sql="DROP TABLE")
    with pytest.raises(ValidationError):
        plan(filters={"conditions": ["x"], "anything": 1})


@pytest.mark.parametrize("n", [1, 5])
def test_plan_needs_two_to_four_groups(n: int) -> None:
    groups = [{"label": f"G{i}", "filters": {"drugs": [f"d{i}"]}} for i in range(n)]
    with pytest.raises(ValidationError, match="2-4"):
        plan(groups=groups)


def test_group_labels_must_be_unique() -> None:
    groups = [{"label": "A", "filters": {"drugs": ["x"]}}, {"label": "A", "filters": {}}]
    with pytest.raises(ValidationError, match="unique"):
        plan(groups=groups)


@pytest.mark.parametrize("field", ["dimension", "dimension_2"])
def test_dimensions_must_be_registry_keys(field: str) -> None:
    with pytest.raises(ValidationError, match="unknown dimension"):
        plan(**{field: "favourite_colour"})


def test_measure_must_be_a_registry_key() -> None:
    with pytest.raises(ValidationError):
        plan(measure="vibes")


def test_metric_plans_have_no_dimension() -> None:
    p = plan(intent="single_number", chart_type="metric", dimension=None)
    assert p.dimension is None


def test_out_of_scope_needs_a_reason() -> None:
    with pytest.raises(ValidationError, match="scope_reason"):
        plan(scope="out_of_scope")
    assert plan(scope="out_of_scope", scope_reason="efficacy question").scope == "out_of_scope"


def test_year_range_is_ordered_and_bounded() -> None:
    with pytest.raises(ValidationError):
        plan(filters={"start_year_min": 2020, "start_year_max": 2015})
    with pytest.raises(ValidationError):
        plan(filters={"start_year_min": 1800})
    with pytest.raises(ValidationError):
        plan(filters={"start_year_max": NEXT_YEAR_LIMIT + 1})


def test_plan_terms_are_cleaned_and_bounded() -> None:
    p = plan(filters={"drugs": ["  Pembrolizumab\n"]})
    assert p.filters.drugs == ["Pembrolizumab"]
    with pytest.raises(ValidationError):
        plan(filters={"drugs": ['""']})
    with pytest.raises(ValidationError):
        plan(filters={"drugs": [f"d{i}" for i in range(11)]})


def test_plan_enum_filters_take_api_codes() -> None:
    p = plan(filters={"phases": ["PHASE2", "PHASE3"], "statuses": ["RECRUITING"]})
    assert [x.value for x in p.filters.phases] == ["PHASE2", "PHASE3"]
    with pytest.raises(ValidationError):
        plan(filters={"phases": ["PHASE7"]})


@pytest.mark.parametrize(("option", "value"), [("top_n", 0), ("top_n", 51)])
def test_plan_options_are_bounded(option: str, value: int) -> None:
    with pytest.raises(ValidationError):
        plan(options={option: value})


# ---------- QueryRequest ----------


def request(**fields: Any) -> QueryRequest:
    return QueryRequest.model_validate({"query": "How are trials distributed by phase?"} | fields)


def test_the_assignment_example_request_is_valid() -> None:
    r = QueryRequest.model_validate(
        {
            "query": "How has the number of trials for this drug changed per year since 2015?",
            "drug_name": "Pembrolizumab",
        }
    )
    assert r.drug_name == ["Pembrolizumab"]


@pytest.mark.parametrize("query", ["", "   ", "x" * 1001])
def test_query_must_be_1_to_1000_chars(query: str) -> None:
    with pytest.raises(ValidationError):
        QueryRequest.model_validate({"query": query})


def test_query_is_trimmed() -> None:
    assert QueryRequest.model_validate({"query": "  hello \n"}).query == "hello"


def test_entity_fields_accept_a_string_or_a_list() -> None:
    r = request(condition=["breast cancer", " lung cancer "], sponsor="Merck")
    assert r.condition == ["breast cancer", "lung cancer"]
    assert r.sponsor == ["Merck"]


@pytest.mark.parametrize("bad", ["", "x" * 201, [f"d{i}" for i in range(11)]])
def test_entity_field_limits(bad: Any) -> None:
    with pytest.raises(ValidationError):
        request(drug_name=bad)


def test_phase_labels_and_codes_are_normalised() -> None:
    r = request(trial_phase=["Phase 3", "phase2", "EARLY_PHASE1", "Not Applicable"])
    assert [p.value for p in r.trial_phase] == ["PHASE3", "PHASE2", "EARLY_PHASE1", "NA"]
    with pytest.raises(ValidationError):
        request(trial_phase=["Phase 7"])


def test_status_labels_and_codes_are_normalised() -> None:
    r = request(status=["Recruiting", "active, not recruiting", "COMPLETED"])
    assert [s.value for s in r.status] == ["RECRUITING", "ACTIVE_NOT_RECRUITING", "COMPLETED"]


def test_year_fields() -> None:
    with pytest.raises(ValidationError):
        request(start_year=2030, end_year=2020)
    with pytest.raises(ValidationError):
        request(start_year=1899)
    assert request(start_year=2015).start_year == 2015


def test_compare_groups() -> None:
    ok = request(compare=[{"label": "A", "drug_name": "x"}, {"label": "B", "drug_name": "y"}])
    assert len(ok.compare) == 2
    with pytest.raises(ValidationError):
        request(compare=[{"label": "A", "drug_name": "x"}])
    with pytest.raises(ValidationError):
        request(compare=[{"label": "A", "drug_name": "x"}, {"label": "B"}])
    with pytest.raises(ValidationError):
        request(compare=[{"label": "A", "drug_name": "x"}, {"label": "A", "drug_name": "y"}])


def test_request_defaults() -> None:
    r = request()
    assert (r.match_mode, r.sponsor_role, r.citations, r.citations_per_datum) == (
        "strict",
        "lead",
        "sample",
        5,
    )
    assert (r.phase_mode, r.condition_source, r.include_unknown) == ("combined", "mesh", True)
    assert (r.edge_metric, r.hide_query_entity) == ("count", False)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("top_n", 0),
        ("top_n", 51),
        ("citations_per_datum", 0),
        ("citations_per_datum", 51),
        ("chart_type", "pie_chart"),
        ("citations", "all"),
    ],
)
def test_request_option_limits(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        request(**{field: value})


def test_unknown_request_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        request(model="gpt-5.4")
