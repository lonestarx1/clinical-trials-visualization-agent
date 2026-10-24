"""Studies -> chart spec + metadata, over the 8 recorded studies (design Q9, Q10, Q12, Q14).

Every expected number was worked out by hand from the jq listing of the samples:

  NCT02648477 PHASE2       COMPLETED              start 2016-03-28 A  enroll 30 A    OTHER   US
  NCT07886905 PHASE2       NOT_YET_RECRUITING     start 2026-12-31 E  enroll 12 E    OTHER   US
  NCT02506153 PHASE3       ACTIVE_NOT_RECRUITING  start 2015-11-10 A  enroll 1301 A  NIH  CA IE US
  NCT04135092 (no phases)  NO_LONGER_AVAILABLE    no start            no enrollment  NIH  no sites
  NCT03724851 PHASE1+2     COMPLETED              start 2018-12-20 A  enroll 120 A   INDUSTRY KR
  NCT04975932 (no phases)  COMPLETED              start 2021-07-01 A  enroll 826 A   OTHER   CN
  NCT05894447 PHASE1       WITHDRAWN              start 2023-11 E     enroll 0 A     OTHER   US
  NCT05834413 NA           RECRUITING             start 2023-05-01 A  enroll 367 E   OTHER   CN
"""

from typing import Any

import pytest

from app.pipeline.charts import ChartResult, build_chart
from app.pipeline.citations import CitationMismatch, verify_citations
from app.schemas.plan import QueryPlan
from tests.support.samples import load_sample, sample_names

STUDIES = [load_sample(n) for n in sample_names()]
BY_ID = {s["protocolSection"]["identificationModule"]["nctId"]: s for s in STUDIES}


def plan(**overrides: Any) -> QueryPlan:
    base: dict[str, Any] = {
        "scope": "in_scope",
        "intent": "distribution",
        "chart_type": "bar_chart",
        "dimension": "phase",
    }
    return QueryPlan.model_validate(base | overrides)


def chart(
    p: QueryPlan, groups: list[tuple[str | None, list[dict]]] | None = None, **kw: Any
) -> ChartResult:
    return build_chart(p, groups or [(None, STUDIES)], now_year=2026, **kw)


def series(result: ChartResult, field: str, value: str = "trial_count") -> list[tuple[Any, Any]]:
    return [(row[field], row[value]) for row in result.visualization.data]  # type: ignore[union-attr]


# ---------- bar charts ----------


def test_phase_distribution_uses_combined_buckets_in_phase_order() -> None:
    result = chart(plan())
    assert series(result, "phase") == [
        ("Phase 1", 1),
        ("Phase 1/Phase 2", 1),
        ("Phase 2", 2),
        ("Phase 3", 1),
        ("Not Applicable", 1),
        ("No phase (observational / expanded access)", 2),
    ]
    assert result.meta.additive is True
    assert result.meta.unique_trials == 8
    assert result.meta.excluded == []
    assert result.meta.counting_rule.startswith("Each trial is counted once")


def test_bar_encoding_names_every_key() -> None:
    viz = chart(plan()).visualization
    assert viz.type == "bar_chart"
    assert viz.encoding["x"].model_dump(exclude_none=True) == {
        "field": "phase",
        "type": "ordinal",
        "label": "Phase",
        "sort": "natural",
    }
    assert viz.encoding["y"].model_dump(exclude_none=True) == {
        "field": "trial_count",
        "type": "quantitative",
        "label": "Number of trials",
        "unit": "trials",
    }


def test_status_distribution() -> None:
    result = chart(plan(dimension="status"))
    assert dict(series(result, "status")) == {
        "Active, not recruiting": 1,
        "Completed": 3,
        "Not yet recruiting": 1,
        "Recruiting": 1,
        "Withdrawn": 1,
        "No longer available": 1,
    }


def test_multi_valued_top_n_is_sorted_and_not_additive() -> None:
    result = chart(plan(intent="top_n", dimension="intervention_type"))
    assert series(result, "intervention_type") == [
        ("Drug", 6),
        ("Biological", 4),
        ("Other", 3),
        ("Procedure", 2),
        ("Device", 1),
        ("Radiation", 1),
    ]
    assert result.meta.additive is False
    assert result.meta.unique_trials == 8


def test_countries_put_not_reported_last() -> None:
    result = chart(plan(intent="geographic", dimension="country"))
    assert series(result, "country") == [
        ("United States", 4),
        ("China", 2),
        ("Canada", 1),
        ("Ireland", 1),
        ("South Korea", 1),
        ("Not reported", 1),
    ]


def test_hidden_unknowns_are_still_counted_as_excluded() -> None:
    result = chart(
        plan(intent="geographic", dimension="country", options={"include_unknown": False})
    )
    assert ("Not reported", 1) not in series(result, "country")
    assert [e.model_dump() for e in result.meta.excluded] == [
        {"reason": "no country reported", "count": 1}
    ]


def test_top_n_limit_is_explained() -> None:
    result = chart(plan(intent="geographic", dimension="country", options={"top_n": 2}))
    assert series(result, "country") == [("United States", 4), ("China", 2), ("Not reported", 1)]
    assert "Showing the top 2 of 5 countries." in result.meta.notes


def test_enrollment_measures() -> None:
    total = chart(plan(dimension="sponsor_class", measure="total_enrollment"))
    assert dict(series(total, "sponsor_class", "total_enrollment")) == {
        "Other (incl. academic)": 1235,
        "NIH": 1301,
        "Industry": 120,
    }
    assert [e.model_dump() for e in total.meta.excluded] == [
        {"reason": "no enrollment reported", "count": 1}
    ]
    median = chart(plan(dimension="sponsor_class", measure="median_enrollment"))
    assert dict(series(median, "sponsor_class", "median_enrollment")) == {
        "Other (incl. academic)": 30,
        "NIH": 1301,
        "Industry": 120,
    }


# ---------- time series ----------


def test_start_year_series_is_zero_filled_and_flags_estimates() -> None:
    result = chart(plan(intent="trend", chart_type="time_series", dimension="start_year"))
    rows = result.visualization.data
    assert [(r["start_year"], r["trial_count"], r["estimated_count"]) for r in rows] == [  # type: ignore[index, union-attr]
        ("2015", 1, 0),
        ("2016", 1, 0),
        ("2017", 0, 0),
        ("2018", 1, 0),
        ("2019", 0, 0),
        ("2020", 0, 0),
        ("2021", 1, 0),
        ("2022", 0, 0),
        ("2023", 2, 1),
        ("2024", 0, 0),
        ("2025", 0, 0),
        ("2026", 1, 1),
    ]
    assert [e.model_dump() for e in result.meta.excluded] == [
        {"reason": "no start date", "count": 1}
    ]
    assert result.visualization.encoding["x"].time_unit == "year"


def test_years_after_the_range_are_excluded_and_counted() -> None:
    result = chart(
        plan(
            intent="trend",
            chart_type="time_series",
            dimension="start_year",
            filters={"start_year_max": 2022},
        )
    )
    assert series(result, "start_year")[-1] == ("2022", 0)
    assert {e.reason: e.count for e in result.meta.excluded} == {
        "no start date": 1,
        "start after 2022": 3,
    }


# ---------- histogram and metric ----------


def test_enrollment_histogram_uses_nice_bins() -> None:
    result = chart(
        plan(intent="numeric_distribution", chart_type="histogram", dimension="enrollment")
    )
    rows = [(r["bin_start"], r["bin_end"], r["count"]) for r in result.visualization.data]  # type: ignore[index, union-attr]
    assert rows == [
        (0, 200, 4),
        (200, 400, 1),
        (400, 600, 0),
        (600, 800, 0),
        (800, 1000, 1),
        (1000, 1200, 0),
        (1200, 1400, 1),
    ]
    assert {e.reason: e.count for e in result.meta.excluded} == {"no enrollment reported": 1}


def test_metric_counts_all_matching_trials() -> None:
    result = chart(plan(intent="single_number", chart_type="metric", dimension=None))
    [row] = result.visualization.data  # type: ignore[misc]
    assert (row["value"], row["citation_count"]) == (8, 8)


# ---------- comparisons ----------


def test_grouped_bars_have_one_row_per_group_and_bucket() -> None:
    first, second = (
        STUDIES[:4],
        STUDIES[4:],
    )  # sorted sample names: combo..missing_start | multi_phase..placebo
    result = chart(
        plan(
            intent="comparison",
            chart_type="grouped_bar_chart",
            dimension="sponsor_class",
            groups=[{"label": "A", "filters": {}}, {"label": "B", "filters": {}}],
        ),
        [("A", first), ("B", second)],
    )
    rows = {(r["group"], r["sponsor_class"]): r["trial_count"] for r in result.visualization.data}  # type: ignore[index, union-attr]
    assert rows == {
        ("A", "NIH"): 2,
        ("A", "Industry"): 0,
        ("A", "Other (incl. academic)"): 2,
        ("B", "NIH"): 0,
        ("B", "Industry"): 1,
        ("B", "Other (incl. academic)"): 3,
    }
    assert result.visualization.encoding["color"].field == "group"
    assert result.meta.group_overlap == [{"groups": ["A", "B"], "trials": 0}]


# ---------- citations ----------


def test_citations_are_ordered_by_most_recent_start_and_counted() -> None:
    row = next(r for r in chart(plan()).visualization.data if r["phase"] == "Phase 2")  # type: ignore[index, union-attr]
    assert row["citation_count"] == 2
    assert [c["nct_id"] for c in row["citations"]] == ["NCT07886905", "NCT02648477"]
    first = row["citations"][0]
    assert first["url"] == "https://clinicaltrials.gov/study/NCT07886905"
    assert first["evidence"] == [
        {"field": "protocolSection.designModule.phases[0]", "excerpt": "PHASE2"}
    ]
    assert row["citations_truncated"] is False


def test_citations_are_truncated_to_the_requested_number() -> None:
    row = chart(plan(dimension="status"), citations_per_datum=1).visualization.data[1]  # type: ignore[index]
    assert row["status"] == "Completed"
    assert (row["citation_count"], len(row["citations"]), row["citations_truncated"]) == (
        3,
        1,
        True,
    )


def test_enrollment_citations_include_the_enrollment_value() -> None:
    result = chart(plan(dimension="sponsor_class", measure="total_enrollment"))
    row = next(r for r in result.visualization.data if r["sponsor_class"] == "Industry")  # type: ignore[index, union-attr]
    assert {"field": "protocolSection.designModule.enrollmentInfo.count", "excerpt": 120} in row[
        "citations"
    ][0]["evidence"]


def test_every_citation_matches_its_record() -> None:
    for p in [
        plan(),
        plan(intent="geographic", dimension="country"),
        plan(intent="trend", chart_type="time_series", dimension="start_year"),
    ]:
        verify_citations(chart(p).visualization, BY_ID)


def test_a_wrong_excerpt_fails_loudly() -> None:
    viz = chart(plan()).visualization
    viz.data[0]["citations"][0]["evidence"][0]["excerpt"] = "PHASE4"  # type: ignore[index]
    with pytest.raises(CitationMismatch):
        verify_citations(viz, BY_ID)


# ---------- scatter ----------


def test_scatter_has_one_point_per_trial_with_both_values() -> None:
    result = chart(
        plan(
            intent="numeric_relationship",
            chart_type="scatter_plot",
            dimension="enrollment",
            dimension_2="duration_months",
        )
    )
    viz = result.visualization
    assert viz.type == "scatter_plot"
    points = {p["nct_id"]: p for p in viz.data}  # type: ignore[union-attr]
    assert len(points) == 7  # NCT04135092 has neither value
    combo = points["NCT02648477"]
    assert combo["enrollment"] == 30
    assert combo["duration_months"] == pytest.approx(93.1, abs=0.05)
    assert combo["citation_count"] == 1
    fields = [e["field"] for e in combo["citations"][0]["evidence"]]
    assert "protocolSection.designModule.enrollmentInfo.count" in fields
    assert "protocolSection.statusModule.completionDateStruct.date" in fields
    assert [e.model_dump() for e in result.meta.excluded] == [
        {"reason": "no enrollment or duration_months reported", "count": 1}
    ]
    assert (viz.encoding["x"].field, viz.encoding["y"].field, viz.encoding["id"].field) == (
        "enrollment",
        "duration_months",
        "nct_id",
    )
    verify_citations(viz, BY_ID)


# ---------- series split by a second dimension ----------


def test_time_series_split_into_series_by_phase() -> None:
    result = chart(
        plan(intent="trend", chart_type="time_series", dimension="start_year", dimension_2="phase")
    )
    viz = result.visualization
    assert viz.encoding["color"].field == "phase"
    rows = {(r["phase"], r["start_year"]): r["trial_count"] for r in viz.data}  # type: ignore[index, union-attr]
    assert rows[("Phase 2", "2016")] == 1 and rows[("Phase 2", "2026")] == 1
    assert rows[("Phase 2", "2015")] == 0
    assert rows[("Phase 3", "2015")] == 1
    series = list(dict.fromkeys(r["phase"] for r in viz.data))  # type: ignore[index, union-attr]
    assert series == [
        "Phase 1",
        "Phase 1/Phase 2",
        "Phase 2",
        "Phase 3",
        "Not Applicable",
        "No phase (observational / expanded access)",
    ]
    assert result.meta.group_overlap is None


def test_bar_chart_split_into_series_becomes_grouped() -> None:
    result = chart(
        plan(
            intent="distribution",
            chart_type="grouped_bar_chart",
            dimension="sponsor_class",
            dimension_2="study_type",
        )
    )
    rows = {
        (r["study_type"], r["sponsor_class"]): r["trial_count"] for r in result.visualization.data
    }  # type: ignore[index, union-attr]
    assert (
        rows[("Interventional", "Other (incl. academic)")] == 4
    )  # combo, future, partial... see table
    # (the observational trial's sponsor is OTHER too)
    assert rows[("Observational", "Other (incl. academic)")] == 1


# ---------- full citation lists (stored for GET /v1/results/{id}/citations) ----------


def test_full_citation_lists_are_kept_per_data_point() -> None:
    result = chart(plan(dimension="status"), citations_per_datum=1)
    completed = result.full_citations["COMPLETED"]
    assert [c["nct_id"] for c in completed] == ["NCT04975932", "NCT03724851", "NCT02648477"]
    assert all("_full" not in row for row in result.visualization.data)  # type: ignore[union-attr]
    assert set(result.full_citations) == {r["key"] for r in result.visualization.data}  # type: ignore[union-attr]


def test_full_citation_lists_for_networks() -> None:
    p = plan(intent="network", chart_type="network_graph", dimension="drug")
    result = chart(p)
    assert len(result.full_citations["drug:pembrolizumab"]) == 5
    assert len(result.full_citations["drug:anastrozole|drug:pembrolizumab"]) == 1


def test_template_summary_formats_large_numbers() -> None:
    """The template is the narrator's fallback; it showed '4228' and '1171' in the UI."""
    result = chart(plan(dimension="sponsor_class", measure="total_enrollment"))
    assert "1,301" in result.visualization.summary
