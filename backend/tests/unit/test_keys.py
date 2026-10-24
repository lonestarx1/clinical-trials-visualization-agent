"""Fast mode (design Q22) in the request and response schemas, and in the plan-cache key."""

from app.core.config import Settings
from app.pipeline.keys import request_key, result_key
from app.schemas.plan import QueryPlan
from app.schemas.request import QueryRequest
from app.schemas.response import Meta


def test_live_is_the_default_mode() -> None:
    assert QueryRequest(query="breast cancer trials by phase").mode == "live"
    assert Meta().data_source == "live"


def test_the_mode_doesnt_change_the_plan_cache_key() -> None:
    """Both modes answer with the same plan, so a plan made in one serves the other."""
    settings = Settings(openai_api_key="test-key-not-real", _env_file=None)  # type: ignore[call-arg]
    live = QueryRequest(query="breast cancer trials by phase")
    fast = QueryRequest(query="breast cancer trials by phase", mode="fast")
    assert request_key(live, settings) == request_key(fast, settings)


def test_each_mode_has_its_own_stored_answers() -> None:
    """A fast answer must never be served to a live request (or the other way round)."""
    plan = QueryPlan.model_validate(
        {
            "scope": "in_scope",
            "intent": "distribution",
            "chart_type": "bar_chart",
            "filters": {"conditions": ["melanoma"]},
            "dimension": "phase",
        }
    )
    assert result_key(plan, 5, "sample", mode="live") != result_key(plan, 5, "sample", mode="fast")
