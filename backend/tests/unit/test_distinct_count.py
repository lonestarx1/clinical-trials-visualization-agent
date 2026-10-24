"""The distinct_count measure: how many distinct entities have at least N trials per bucket.

Fixture, worked out by hand (lead sponsor per trial, start year):

  2015: N1 Alpha, N2 Alpha, N3 Alpha, N4 Beta, N5 Beta, N6 Gamma
  2016: N7 alpha (same sponsor, other case), N8 Beta, N9 Beta, N10 Beta

  min 1 -> 2015: 3 (Alpha, Beta, Gamma)   2016: 2 (Alpha, Beta)
  min 2 -> 2015: 2 (Alpha 3, Beta 2)      2016: 1 (Beta 3)
  min 3 -> 2015: 1 (Alpha: N1-N3)         2016: 1 (Beta: N8-N10)
  whole set: Alpha 4, Beta 5, Gamma 1 -> min 3: 2, min 5: 1
"""

from typing import Any

import pytest
from pydantic import ValidationError

from app.pipeline.charts import ChartResult, build_chart
from app.pipeline.citations import verify_citations
from app.schemas.plan import QueryPlan

SPONSOR_PATH = "protocolSection.sponsorCollaboratorsModule.leadSponsor.name"


def study(nct: str, year: int, sponsor: str) -> dict[str, Any]:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": f"Trial {nct}"},
            "statusModule": {"startDateStruct": {"date": f"{year}-03-01", "type": "ACTUAL"}},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": sponsor, "class": "OTHER"}},
        }
    }


STUDIES = [
    study("N1", 2015, "Alpha"),
    study("N2", 2015, "Alpha"),
    study("N3", 2015, "Alpha"),
    study("N4", 2015, "Beta"),
    study("N5", 2015, "Beta"),
    study("N6", 2015, "Gamma"),
    study("N7", 2016, "alpha"),
    study("N8", 2016, "Beta"),
    study("N9", 2016, "Beta"),
    study("N10", 2016, "Beta"),
]
BY_ID = {s["protocolSection"]["identificationModule"]["nctId"]: s for s in STUDIES}


def plan(min_trials: int = 1, **overrides: Any) -> QueryPlan:
    base: dict[str, Any] = {
        "scope": "in_scope",
        "intent": "trend",
        "chart_type": "time_series",
        "dimension": "start_year",
        "measure": "distinct_count",
        "filters": {"start_year_min": 2015, "start_year_max": 2016},
        "options": {"count_entity": "sponsor", "min_trials": min_trials},
    }
    return QueryPlan.model_validate(base | overrides)


def chart(p: QueryPlan) -> ChartResult:
    result = build_chart(p, [(None, STUDIES)], now_year=2026, citations_per_datum=10)
    verify_citations(result.visualization, BY_ID)
    return result


def per_year(result: ChartResult) -> list[tuple[Any, Any]]:
    return [(r["start_year"], r["distinct_count"]) for r in result.visualization.data]  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("min_trials", "expected"),
    [
        (1, [("2015", 3), ("2016", 2)]),
        (2, [("2015", 2), ("2016", 1)]),
        (3, [("2015", 1), ("2016", 1)]),
    ],
)
def test_counts_distinct_sponsors_with_at_least_n_trials_per_year(
    min_trials: int, expected: list[tuple[str, int]]
) -> None:
    assert per_year(chart(plan(min_trials))) == expected


def test_citations_are_the_trials_of_qualifying_sponsors_with_the_sponsor_line() -> None:
    rows = chart(plan(3)).visualization.data
    cited = [sorted(c["nct_id"] for c in r["citations"]) for r in rows]  # type: ignore[index]
    assert cited == [["N1", "N2", "N3"], ["N10", "N8", "N9"]]
    assert [r["citation_count"] for r in rows] == [3, 3]  # type: ignore[index]
    fields = {e["field"] for r in rows for c in r["citations"] for e in c["evidence"]}  # type: ignore[index]
    assert SPONSOR_PATH in fields


def test_axis_label_rule_and_additivity_name_the_entity_and_threshold() -> None:
    result = chart(plan(3))
    y = result.visualization.encoding["y"]
    assert y.label == "Lead sponsors with at least 3 trials"
    assert y.unit == "lead sponsors"
    assert result.meta.additive is False
    assert "distinct lead sponsors with at least 3 matching trials" in result.meta.counting_rule


def test_threshold_of_one_is_a_plain_count_of_sponsors() -> None:
    assert chart(plan(1)).visualization.encoding["y"].label == "Number of lead sponsors"


@pytest.mark.parametrize(("min_trials", "expected"), [(3, 2), (5, 1)])
def test_metric_counts_sponsors_over_the_whole_set(min_trials: int, expected: int) -> None:
    p = plan(min_trials, intent="single_number", chart_type="metric", dimension=None)
    row = chart(p).visualization.data[0]  # type: ignore[index]
    assert row["value"] == expected


def test_plan_needs_an_entity_to_count() -> None:
    with pytest.raises(ValidationError, match="count_entity"):
        plan(options={"min_trials": 2})
    with pytest.raises(ValidationError, match="count_entity"):
        plan(options={"count_entity": "phase"})


def test_min_trials_is_bounded() -> None:
    with pytest.raises(ValidationError):
        plan(0)
