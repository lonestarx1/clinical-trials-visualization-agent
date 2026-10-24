"""The AI evaluation cases stay valid against the schemas and the registry (design Q18)."""

from typing import Any

import pytest

from app.registry import DIMENSIONS, MEASURES, ChartType
from app.registry.charts import Intent
from app.schemas.plan import Filters, QueryPlan
from app.schemas.request import QueryRequest
from app.validation.gate import check_plan
from evals.cases import (
    EXPECT_KEYS,
    load_guard_cases,
    load_narrator_cases,
    load_planner_cases,
)

PLANNER = load_planner_cases()
GUARD = load_guard_cases()
NARRATOR = load_narrator_cases()


def first_option(value: Any) -> Any:
    return value["any_of"][0] if isinstance(value, dict) and "any_of" in value else value


def options(value: Any) -> list[Any]:
    return value["any_of"] if isinstance(value, dict) and "any_of" in value else [value]


def test_set_sizes_and_unique_ids() -> None:
    assert len(PLANNER) >= 40
    assert sum(c.expected == "malicious" for c in GUARD) >= 12
    assert sum(c.expected == "ok" for c in GUARD) >= 15
    assert sum(c.expected == "off_topic" for c in GUARD) >= 4
    assert len(NARRATOR) >= 10
    for cases in (PLANNER, GUARD, NARRATOR):
        ids = [c.id for c in cases]
        assert len(ids) == len(set(ids))


def test_every_appendix_question_is_a_planner_case() -> None:
    assert {f"PA-{i}" for i in range(1, 10)} <= {c.id for c in PLANNER}


@pytest.mark.parametrize("case", PLANNER, ids=lambda c: c.id)
def test_planner_expectations_use_real_values(case: Any) -> None:
    QueryRequest.model_validate(case.request)
    expect = case.expect
    assert set(expect) <= EXPECT_KEYS
    for value in options(expect.get("chart_type")):
        assert value is None or value in set(ChartType)
    for value in options(expect.get("intent")):
        assert value is None or value in set(Intent)
    for key in ("dimension", "dimension_2"):
        for value in options(expect.get(key)):
            assert value is None or value in DIMENSIONS
    for value in options(expect.get("measure")):
        assert value is None or value in MEASURES
    for value in options(expect.get("options", {}).get("count_entity")):
        assert value is None or value in DIMENSIONS
    Filters.model_validate({k: first_option(v) for k, v in expect.get("filters", {}).items()})
    for group in expect.get("groups", []):
        Filters.model_validate(group)


@pytest.mark.parametrize("case", GUARD, ids=lambda c: c.id)
def test_guard_cases_are_valid_requests(case: Any) -> None:
    QueryRequest.model_validate(case.request)
    assert case.expected in ("ok", "off_topic", "malicious")


@pytest.mark.parametrize("case", NARRATOR, ids=lambda c: c.id)
def test_narrator_plans_pass_the_gate(case: Any) -> None:
    QueryPlan.model_validate(case.plan)
    gate = check_plan(case.plan, QueryRequest(query=case.question), final=True)
    assert not gate.errors, gate.errors
