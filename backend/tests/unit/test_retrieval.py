"""Field selection and count-per-bucket retrieval (design Q6, strategy S2)."""

from typing import Any

import pytest

from app.ctgov.client import InconsistentResults
from app.ctgov.compiler import Search
from app.ctgov.essie import Area, Code, Missing
from app.ctgov.retrieval import count_per_bucket, fields_for
from app.registry import DIMENSIONS
from app.schemas.plan import QueryPlan


def _plan(**overrides: Any) -> QueryPlan:
    base: dict[str, Any] = {
        "scope": "in_scope",
        "intent": "distribution",
        "chart_type": "bar_chart",
        "dimension": "phase",
    }
    return QueryPlan.model_validate(base | overrides)


def test_fields_for_a_phase_distribution() -> None:
    assert fields_for(_plan()) == ["NCTId", "BriefTitle", "StartDate", "Phase", "StudyType"]


def test_fields_are_unique_and_include_the_measure_and_second_dimension() -> None:
    plan = _plan(
        intent="network",
        chart_type="network_graph",
        dimension="sponsor",
        dimension_2="drug",
        measure="total_enrollment",
    )
    assert fields_for(plan) == [
        "NCTId",
        "BriefTitle",
        "StartDate",
        "LeadSponsorName",
        "LeadSponsorClass",
        "InterventionName",
        "InterventionType",
        "InterventionMeshTerm",
        "EnrollmentCount",
        "EnrollmentType",
    ]


def test_narrow_adds_a_clause_to_filter_advanced() -> None:
    clause = Area("Phase", Code("PHASE3"))
    assert Search({"query.cond": '"x"'}).narrow(clause).params == {
        "query.cond": '"x"',
        "filter.advanced": "AREA[Phase]PHASE3",
    }
    assert Search({"filter.advanced": "AREA[StudyType]INTERVENTIONAL"}).narrow(clause).params == {
        "filter.advanced": "(AREA[StudyType]INTERVENTIONAL AND AREA[Phase]PHASE3)"
    }


class FakeCounter:
    """Answers count() from a table keyed by the narrowing clause."""

    def __init__(self, total: int, per_clause: dict[str, int]) -> None:
        self.total, self.per_clause = total, per_clause
        self.searches: list[Search] = []

    async def count(self, search: Search) -> int:
        self.searches.append(search)
        advanced = search.params.get("filter.advanced", "")
        for clause, n in self.per_clause.items():
            if advanced.endswith(clause) or advanced.endswith(clause + ")"):
                return n
        return self.total


async def test_count_per_bucket_counts_every_value_and_missing() -> None:
    counts = {
        "AREA[StudyType]INTERVENTIONAL": 70,
        "AREA[StudyType]OBSERVATIONAL": 25,
        "AREA[StudyType]EXPANDED_ACCESS": 3,
        "AREA[StudyType]MISSING": 2,
    }
    counter = FakeCounter(total=100, per_clause=counts)
    result = await count_per_bucket(
        counter, Search({"query.cond": '"x"'}), DIMENSIONS["study_type"]
    )

    assert result.total == 100
    assert result.buckets == {"EXPANDED_ACCESS": 3, "INTERVENTIONAL": 70, "OBSERVATIONAL": 25}
    assert result.missing == 2
    assert all(s.params["query.cond"] == '"x"' for s in counter.searches)


async def test_single_valued_buckets_must_add_up_to_the_total() -> None:
    counts = {
        "AREA[StudyType]INTERVENTIONAL": 70,
        "AREA[StudyType]OBSERVATIONAL": 25,
        "AREA[StudyType]EXPANDED_ACCESS": 3,
        "AREA[StudyType]MISSING": 0,
    }
    with pytest.raises(InconsistentResults, match="98"):
        await count_per_bucket(FakeCounter(100, counts), Search({}), DIMENSIONS["study_type"])


async def test_multi_valued_buckets_may_exceed_the_total() -> None:
    counts = {
        f"AREA[InterventionType]{v}": 60
        for v in [
            "BEHAVIORAL",
            "BIOLOGICAL",
            "COMBINATION_PRODUCT",
            "DEVICE",
            "DIAGNOSTIC_TEST",
            "DIETARY_SUPPLEMENT",
            "DRUG",
            "GENETIC",
            "PROCEDURE",
            "RADIATION",
            "OTHER",
        ]
    }
    counts["AREA[InterventionType]MISSING"] = 0
    result = await count_per_bucket(
        FakeCounter(100, counts), Search({}), DIMENSIONS["intervention_type"]
    )
    assert sum(result.buckets.values()) == 660


def test_missing_clause_is_well_formed() -> None:
    assert Search({}).narrow(Area("Phase", Missing())).params == {
        "filter.advanced": "AREA[Phase]MISSING"
    }


async def test_count_per_bucket_needs_a_bounded_dimension() -> None:
    with pytest.raises(ValueError, match="bounded"):
        await count_per_bucket(FakeCounter(1, {}), Search({}), DIMENSIONS["drug"])
