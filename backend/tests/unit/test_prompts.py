"""What the planner and guard prompts must spell out (found by the AI eval, docs/eval)."""

from app.agents import guard, planner
from app.registry import ChartType
from app.schemas.plan import PlanOptions


def test_the_planner_prompt_lists_the_exact_chart_types() -> None:
    """The planner guessed chart_type "bar" on most first submissions, costing a step."""
    built = [c.value for c in ChartType if c not in planner.NOT_BUILT_YET]
    assert all(f'"{c}"' in planner.INSTRUCTIONS for c in built)


def test_the_planner_prompt_names_every_option_and_top_n() -> None:
    """It never set top_n ("the 5 most common") and once sent options.n."""
    assert all(f"{name}" in planner.INSTRUCTIONS for name in PlanOptions.model_fields)
    assert '"top 5" means top_n 5' in planner.INSTRUCTIONS


def test_the_guard_prompt_calls_writing_requests_misuse() -> None:
    """It labelled "Write a 1000-word essay about ..." off_topic, not malicious."""
    assert "however harmless the topic" in guard.INSTRUCTIONS
    assert "off_topic" in guard.INSTRUCTIONS and "questions" in guard.INSTRUCTIONS


def test_the_planner_prompt_never_drops_a_named_term() -> None:
    """It dropped "melanoma" from "intervention types for melanoma trials" (PA-4, 1 run in 3)."""
    assert "Never drop one" in planner.INSTRUCTIONS


def test_the_guard_prompt_keeps_advice_questions_off_topic_and_filters_ok() -> None:
    """After the misuse rule, "How do I bake sourdough bread?" became malicious, and
    "Ignore trials without a start date ..." was still blocked."""
    assert "cooking" in guard.INSTRUCTIONS and "shopping" in guard.INSTRUCTIONS
    assert "ignore trials without a start date" in guard.INSTRUCTIONS
