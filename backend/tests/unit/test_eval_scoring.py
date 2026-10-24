"""Scoring for the AI evaluation set (design Q18, Q20): plan properties, stage metrics, bars."""

from typing import Any

from evals.scoring import (
    GuardRun,
    NarratorRun,
    PlannerRun,
    choose,
    guard_summary,
    narrator_summary,
    percentile,
    planner_summary,
    same_term,
    score_plan,
)

PLAN: dict[str, Any] = {
    "scope": "in_scope",
    "intent": "distribution",
    "chart_type": "bar_chart",
    "filters": {"conditions": ["Breast Cancer"], "phases": ["PHASE3", "PHASE2"]},
    "dimension": "phase",
    "measure": "trial_count",
    "groups": [],
    "options": {"top_n": 10},
}


def test_terms_match_case_and_containment_insensitively() -> None:
    assert same_term("breast cancer", "Breast Cancer")
    assert same_term("Korea", "Korea, Republic of")
    assert same_term("pembrolizumab (Keytruda)", "pembrolizumab")
    assert not same_term("lung cancer", "breast cancer")


def test_a_matching_plan_passes_every_property() -> None:
    expect = {
        "scope": "in_scope",
        "chart_type": "bar_chart",
        "dimension": "phase",
        "filters": {"conditions": ["breast cancer"], "phases": ["PHASE2", "PHASE3"]},
        "options": {"top_n": 10},
    }
    assert score_plan(expect, PLAN) == {
        "scope": True,
        "chart_type": True,
        "dimension": True,
        "filters.conditions": True,
        "filters.phases": True,
        "filters.extra": True,
        "options.top_n": True,
    }


def test_wrong_values_and_unasked_filters_fail() -> None:
    expect = {"dimension": "status", "filters": {"conditions": ["breast cancer"]}}
    scores = score_plan(expect, PLAN)
    assert scores["dimension"] is False
    assert scores["filters.conditions"] is True
    assert scores["filters.extra"] is False  # phases were not asked for


def test_unasked_filters_can_be_allowed() -> None:
    expect = {"filters": {"conditions": ["breast cancer"]}, "extra_filters_ok": True}
    assert score_plan(expect, PLAN)["filters.extra"] is True


def test_any_of_accepts_alternatives() -> None:
    expect = {
        "chart_type": {"any_of": ["metric", "bar_chart"]},
        "filters": {
            "phases": {"any_of": [["PHASE3"], ["PHASE2", "PHASE3"]]},
            "conditions": ["breast cancer"],
        },
    }
    scores = score_plan(expect, PLAN)
    assert scores["chart_type"] and scores["filters.phases"]


def test_term_lists_need_the_same_terms_no_more_no_fewer() -> None:
    assert not score_plan({"filters": {"conditions": ["breast cancer", "lung cancer"]}}, PLAN)[
        "filters.conditions"
    ]
    extra = PLAN | {"filters": {"conditions": ["breast cancer", "breast neoplasms"]}}
    assert not score_plan({"filters": {"conditions": ["breast cancer"]}}, extra)[
        "filters.conditions"
    ]


def test_groups_match_in_any_order() -> None:
    plan = PLAN | {
        "chart_type": "grouped_bar_chart",
        "filters": {},
        "groups": [
            {"label": "Nivolumab", "filters": {"drugs": ["nivolumab"]}},
            {"label": "Pembrolizumab", "filters": {"drugs": ["pembrolizumab"]}},
        ],
    }
    expect = {"groups": [{"drugs": ["pembrolizumab"]}, {"drugs": ["nivolumab"]}]}
    assert score_plan(expect, plan)["groups"] is True
    assert score_plan({"groups": [{"drugs": ["pembrolizumab"]}]}, plan)["groups"] is False


def test_no_plan_fails_every_expected_property() -> None:
    scores = score_plan({"scope": "in_scope", "filters": {"drugs": ["x"]}}, None)
    assert scores == {"scope": False, "filters.drugs": False, "filters.extra": False}


def test_out_of_scope_checks_the_suggestion_when_asked() -> None:
    plan = {"scope": "out_of_scope", "scope_reason": "no measure", "scope_suggestion": None}
    assert score_plan({"scope": "out_of_scope", "has_suggestion": True}, plan) == {
        "scope": True,
        "has_suggestion": False,
    }


def test_percentile_is_nearest_rank() -> None:
    values = [float(v) for v in range(1, 21)]
    assert percentile(values, 50) == 10
    assert percentile(values, 95) == 19
    assert percentile([], 50) is None


def test_planner_summary_and_bars() -> None:
    runs = [
        PlannerRun("a", 1, {"scope": True, "dimension": True}, True, True, 2, 1000, 0.002),
        PlannerRun("b", 1, {"scope": True, "dimension": False}, True, False, 4, 3000, 0.004),
    ]
    summary = planner_summary(runs)
    assert summary["fully_correct"] == 0.5
    assert summary["property_accuracy"] == {"dimension": 0.5, "scope": 1.0}
    assert summary["valid"] == 1.0 and summary["first_try"] == 0.5
    assert summary["avg_steps"] == 3 and summary["cost_per_question"] == 0.003
    assert summary["failed_cases"] == ["b"]
    assert summary["bars"] == {
        "fully_correct >= 90%": False,
        "valid >= 99%": True,
        "p95 <= 15 s": True,
    }


def test_guard_summary_reports_recall_and_false_positives() -> None:
    runs = [
        GuardRun("m1", 1, "malicious", "malicious", 500, 0.0001),
        GuardRun("m2", 1, "malicious", "ok", 500, 0.0001),
        GuardRun("o1", 1, "ok", "ok", 700, 0.0001),
        GuardRun("o2", 1, "ok", "off_topic", 900, 0.0001),
        GuardRun("t1", 1, "off_topic", "off_topic", 600, 0.0001),
    ]
    summary = guard_summary(runs)
    assert summary["malicious_recall"] == 0.5
    assert summary["false_positive_rate"] == 0.5
    assert summary["off_topic_accuracy"] == 1.0
    assert summary["missed"] == ["m2"] and summary["false_positives"] == ["o2"]
    assert summary["bars"]["malicious recall = 100%"] is False


def test_narrator_summary() -> None:
    runs = [
        NarratorRun("a", 1, "Title A", 1, False, 800, 0.0001),
        NarratorRun("b", 1, "Title B", 2, False, 2000, 0.0002),
        NarratorRun("c", 1, "Fallback", 2, True, 2500, 0.0002),
    ]
    summary = narrator_summary(runs)
    assert summary["first_attempt"] == round(1 / 3, 3)
    assert summary["fallback"] == round(1 / 3, 3)
    assert summary["bars"]["first attempt >= 95%"] is False


def test_choose_takes_the_cheapest_candidate_that_passes_every_bar() -> None:
    summaries = {
        "big": {"bars": {"a": True}, "cost_per_call": 0.010, "p95_ms": 900},
        "small": {"bars": {"a": True}, "cost_per_call": 0.002, "p95_ms": 2000},
        "tiny": {"bars": {"a": False}, "cost_per_call": 0.001, "p95_ms": 500},
    }
    assert choose(summaries) == "small"


def test_choose_prefers_the_faster_of_two_within_20_percent_on_cost() -> None:
    summaries = {
        "a": {"bars": {"x": True}, "cost_per_question": 0.0020, "p95_ms": 4000},
        "b": {"bars": {"x": True}, "cost_per_question": 0.0023, "p95_ms": 2500},
    }
    assert choose(summaries) == "b"


def test_choose_returns_none_when_no_candidate_passes() -> None:
    assert choose({"a": {"bars": {"x": False}, "cost_per_call": 0.001, "p95_ms": 1}}) is None


def test_planner_summary_names_the_failed_properties_per_case() -> None:
    runs = [
        PlannerRun("b", 1, {"dimension": False, "scope": True}, True, False, 4, 3000, 0.004),
        PlannerRun("b", 2, {"dimension": False, "scope": False}, True, False, 4, 3000, 0.004),
        PlannerRun("c", 1, {"dimension": True}, True, True, 1, 900, 0.001),
    ]
    assert planner_summary(runs)["failures"] == {"b": {"dimension": 2, "scope": 1}}


def test_a_base_filter_repeating_the_groups_terms_is_not_an_extra_filter() -> None:
    """(A or B) and A is A: the chart is the same, so it isn't a wrong filter."""
    plan = PLAN | {
        "chart_type": "grouped_bar_chart",
        "filters": {"drugs": ["pembrolizumab", "nivolumab"], "sponsor_role": "any"},
        "groups": [
            {"label": "P", "filters": {"drugs": ["pembrolizumab"]}},
            {"label": "N", "filters": {"drugs": ["nivolumab"]}},
        ],
    }
    expect = {"groups": [{"drugs": ["pembrolizumab"]}, {"drugs": ["nivolumab"]}], "filters": {}}
    assert score_plan(expect, plan)["filters.extra"] is True


def test_a_base_filter_narrower_than_the_groups_is_still_extra() -> None:
    plan = PLAN | {
        "filters": {"drugs": ["pembrolizumab"]},
        "groups": [
            {"label": "P", "filters": {"drugs": ["pembrolizumab"]}},
            {"label": "N", "filters": {"drugs": ["nivolumab"]}},
        ],
    }
    expect = {"groups": [{"drugs": ["pembrolizumab"]}, {"drugs": ["nivolumab"]}], "filters": {}}
    assert score_plan(expect, plan)["filters.extra"] is False
