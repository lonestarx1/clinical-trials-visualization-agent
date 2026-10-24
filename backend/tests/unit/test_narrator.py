"""Narrator (design Q4b V5-V9): fact sheet + placeholders, text checks, retry, template fallback."""

from typing import Any

import pytest

from app.agents.narrator import check_text, fact_sheet, narrate, render
from app.llm.client import LLMUnavailable
from app.pipeline.charts import build_chart
from app.schemas.plan import QueryPlan
from tests.support.fake_llm import ScriptedLLM, text
from tests.support.samples import load_sample, sample_names

STUDIES = [load_sample(n) for n in sample_names()]


def chart(**overrides: Any):  # type: ignore[no-untyped-def]
    base = {
        "scope": "in_scope",
        "intent": "distribution",
        "chart_type": "bar_chart",
        "filters": {"conditions": ["breast cancer"]},
        "dimension": "phase",
    }
    plan = QueryPlan.model_validate(base | overrides)
    return plan, build_chart(plan, [(None, STUDIES)], now_year=2026)


def test_fact_sheet_for_a_bar_chart() -> None:
    plan, result = chart()
    facts = fact_sheet(plan, result.visualization, result.meta)
    assert facts["total"] == "8"
    assert (facts["max_bucket"], facts["max_value"]) == ("Phase 2", "2")
    assert facts["n_buckets"] == "6"
    assert facts["dimension"] == "phase"
    assert facts["scope"] == "breast cancer"
    assert facts["share_of_max"] == "25%"
    # runners-up exclude the leader (a live summary said "China leads, followed by China")
    assert (
        facts["next_items"]
        == "No phase (observational / expanded access), Phase 1, Phase 1/Phase 2"
    )
    assert "top_items" not in facts


def test_fact_sheet_for_a_time_series() -> None:
    plan, result = chart(intent="trend", chart_type="time_series", dimension="start_year")
    facts = fact_sheet(plan, result.visualization, result.meta)
    assert (facts["first_bucket"], facts["last_bucket"]) == ("2015", "2026")
    assert (facts["max_bucket"], facts["max_value"]) == ("2023", "2")


def test_render_fills_placeholders() -> None:
    assert render(
        "{max_bucket} leads with {max_value}", {"max_bucket": "Phase 2", "max_value": "2"}
    ) == ("Phase 2 leads with 2")
    with pytest.raises(KeyError):
        render("{made_up}", {})


def _check(template: str) -> list[str]:
    plan, result = chart()
    facts = fact_sheet(plan, result.visualization, result.meta)
    return check_text(template, facts, plan, result.visualization, max_length=200)


def test_numbers_must_be_placeholders_or_fact_values() -> None:
    assert _check("{total} breast cancer trials; {max_bucket} has {max_value}.") == []
    assert _check("8 trials matched.") == []  # equals a fact
    assert any("37" in e for e in _check("37 trials matched."))


def test_named_categories_must_be_in_the_chart() -> None:
    assert _check("Most trials are Phase 2.") == []
    assert any("Phase 4" in e for e in _check("Phase 4 trials are rare."))


@pytest.mark.parametrize("word", ["effective", "safest", "proves", "superior", "promising"])
def test_evaluative_claims_are_banned(word: str) -> None:
    assert any(word in e for e in _check(f"Phase 2 looks {word}."))


@pytest.mark.parametrize(
    "template", ["{facts.total} trials.", "{max value} trials.", "{} trials.", "{total"]
)
def test_malformed_placeholders_are_rejected(template: str) -> None:
    """Found in a live run: the model wrote {facts.min_bucket}, which went out unrendered."""
    assert any("placeholder" in e for e in _check(template))


def test_unknown_placeholders_and_length() -> None:
    assert any("unknown placeholder" in e for e in _check("{nonsense} trials."))
    assert any("too long" in e for e in _check("x" * 201))


async def test_narrate_uses_the_model_text() -> None:
    plan, result = chart()
    summary = "{max_bucket} is the most common phase, with {max_value} of {total} trials."
    llm = ScriptedLLM(text({"title": "Breast cancer trials by phase", "summary": summary}))
    n = await narrate(llm, plan, result.visualization, result.meta)
    assert n.title == "Breast cancer trials by phase"
    assert n.summary == "Phase 2 is the most common phase, with 2 of 8 trials."
    assert (n.attempts, n.fallback) == (1, False)
    assert "max_value" in llm.prompt_text()  # the model sees fact names


async def test_narrate_retries_with_the_errors_then_succeeds() -> None:
    plan, result = chart()
    llm = ScriptedLLM(
        text({"title": "Phase 2 is the most effective", "summary": "{total} trials."}),
        text({"title": "Trials by phase", "summary": "{total} trials matched."}),
    )
    n = await narrate(llm, plan, result.visualization, result.meta)
    assert (n.attempts, n.fallback, n.title) == (2, False, "Trials by phase")
    assert "effective" in llm.prompt_text(1)  # the retry names the problem


@pytest.mark.parametrize(
    "replies",
    [
        (
            text({"title": "Best phase", "summary": "x"}),
            text({"title": "Cure found", "summary": "y"}),
        ),
        (LLMUnavailable("down"),),
    ],
)
async def test_narrate_falls_back_to_the_template(replies: tuple[Any, ...]) -> None:
    plan, result = chart()
    n = await narrate(ScriptedLLM(*replies), plan, result.visualization, result.meta)
    assert n.fallback is True
    assert (n.title, n.summary) == (result.visualization.title, result.visualization.summary)
    assert n.errors


def test_no_share_of_total_for_comparisons() -> None:
    """Groups can overlap, so a bar's share of all trials is misleading (seen in a live run)."""
    plan = QueryPlan.model_validate(
        {
            "scope": "in_scope",
            "intent": "comparison",
            "chart_type": "grouped_bar_chart",
            "dimension": "phase",
            "groups": [{"label": "A", "filters": {}}, {"label": "B", "filters": {}}],
        }
    )
    result = build_chart(plan, [("A", STUDIES[:4]), ("B", STUDIES[4:])], now_year=2026)
    facts = fact_sheet(plan, result.visualization, result.meta)
    assert "share_of_max" not in facts
    assert facts["max_group"] in ("A", "B")


def test_fact_sheet_for_a_network() -> None:
    plan = QueryPlan.model_validate(
        {
            "scope": "in_scope",
            "intent": "network",
            "chart_type": "network_graph",
            "dimension": "drug",
        }
    )
    result = build_chart(plan, [(None, STUDIES)], now_year=2026)
    facts = fact_sheet(plan, result.visualization, result.meta)
    assert (facts["n_nodes"], facts["n_edges"], facts["total"]) == ("15", "29", "5")
    assert (facts["top_node"], facts["top_node_degree"]) == ("pembrolizumab", "14")
    assert facts["strongest_link"].count(" - ") == 1
    assert (
        _check_for(plan, result, "{n_nodes} drugs, {n_edges} links; {top_node} is most connected.")
        == []
    )


def _check_for(plan: QueryPlan, result: Any, template: str) -> list[str]:
    facts = fact_sheet(plan, result.visualization, result.meta)
    return check_text(template, facts, plan, result.visualization, max_length=200)


def test_fact_sheet_for_a_scatter_plot() -> None:
    plan = QueryPlan.model_validate(
        {
            "scope": "in_scope",
            "intent": "numeric_relationship",
            "chart_type": "scatter_plot",
            "dimension": "enrollment",
            "dimension_2": "duration_months",
        }
    )
    result = build_chart(plan, [(None, STUDIES)], now_year=2026)
    facts = fact_sheet(plan, result.visualization, result.meta)
    # enrollments 0, 12, 30, 120, 367, 826, 1301 -> median 120
    assert (facts["n_points"], facts["median_x"]) == ("7", "120")
    assert "max_bucket" not in facts


@pytest.mark.parametrize(
    "title",
    [
        "ClinicalTrials.gov: Trials by phase",
        "ClinicalTrials.gov trials by phase",
        "Trials by phase",
    ],
)
async def test_titles_do_not_start_with_the_source_name(title: str) -> None:
    """Every chart is from ClinicalTrials.gov; repeating it in each title is noise (seen live)."""
    plan, result = chart()
    n = await narrate(
        ScriptedLLM(text({"title": title, "summary": "{total} trials."})),
        plan,
        result.visualization,
        result.meta,
    )
    assert n.title in ("Trials by phase", "trials by phase".capitalize())
    assert not n.title.lower().startswith("clinicaltrials")
