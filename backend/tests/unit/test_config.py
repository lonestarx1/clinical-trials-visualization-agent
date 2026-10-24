"""Settings (design Q19 limits, Q20 per-stage model settings)."""

import os

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.pricing import load_pricing, missing_prices

PREFIXES = ("OPENAI_", "GUARD_", "PLANNER_", "NARRATOR_", "CTGOV_", "LLM_", "DATABASE_")


@pytest.fixture
def make_settings(monkeypatch: pytest.MonkeyPatch):
    """Build Settings from a clean environment, never from the real .env file."""
    for name in list(os.environ):
        if name.startswith(PREFIXES):
            monkeypatch.delenv(name)

    def _make(**env: str) -> Settings:
        env.setdefault("OPENAI_API_KEY", "test-key-not-real")
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return Settings(_env_file=None)

    return _make


def test_stage_defaults_match_the_design(make_settings) -> None:
    """The bake-off's choices (docs/eval/model-selection.md, design Q20)."""
    s = make_settings()
    assert (s.guard.model, s.planner.model, s.narrator.model) == (
        "gpt-5.4-nano",
        "gpt-5.4-mini",
        "gpt-4o-mini",
    )
    # gpt-4.1-mini scored 83% as a planner, so the planner falls back to gpt-5-mini (99%).
    assert (s.guard.fallback_model, s.planner.fallback_model, s.narrator.fallback_model) == (
        "gpt-4.1-mini",
        "gpt-5-mini",
        "gpt-4.1-mini",
    )
    assert (s.guard.timeout_seconds, s.planner.timeout_seconds, s.narrator.timeout_seconds) == (
        5,
        30,
        10,
    )
    assert s.planner.reasoning_effort == "low"
    assert s.planner.max_steps == 6


def test_limit_defaults_match_the_design(make_settings) -> None:
    s = make_settings()
    assert s.rate_limit_per_ip_per_min == 300
    assert s.max_active_jobs_per_ip == 10
    assert s.llm_daily_budget_usd == 100
    assert s.ctgov_rate_limit_per_min == 54
    assert s.ctgov_rate_burst == 9
    assert s.ctgov_max_concurrency == 9
    assert s.ctgov_count_cache_seconds == 600
    assert s.mirror_sync_enabled is False
    assert s.mirror_sync_rate_per_min == 27
    assert s.sync_max_seconds == 60
    assert s.citations_full_max == 2000
    assert s.llm_startup_ping is False


def test_openai_key_is_required(make_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="openai_api_key"):
        make_settings(OPENAI_API_KEY="")


def test_openai_key_never_appears_in_repr(make_settings) -> None:
    s = make_settings(OPENAI_API_KEY="sk-should-stay-hidden")
    assert "sk-should-stay-hidden" not in repr(s)
    assert s.openai_api_key.get_secret_value() == "sk-should-stay-hidden"


def test_stage_settings_come_from_prefixed_env_vars(make_settings) -> None:
    s = make_settings(
        PLANNER_MODEL="gpt-5.4",
        PLANNER_REASONING_EFFORT="medium",
        PLANNER_MAX_STEPS="8",
        NARRATOR_TEMPERATURE="0.2",
    )
    assert s.planner.model == "gpt-5.4"
    assert s.planner.reasoning_effort == "medium"
    assert s.planner.max_steps == 8
    assert s.narrator.temperature == 0.2
    assert s.guard.model == "gpt-5.4-nano"


def test_primary_and_fallback_models_must_differ(make_settings) -> None:
    with pytest.raises(ValidationError, match="fallback"):
        make_settings(GUARD_MODEL="gpt-4.1-mini")


def test_fallback_can_be_disabled(make_settings) -> None:
    assert make_settings(PLANNER_FALLBACK_MODEL="").planner.fallback_model is None


def test_unknown_reasoning_effort_is_rejected(make_settings) -> None:
    with pytest.raises(ValidationError):
        make_settings(PLANNER_REASONING_EFFORT="extreme")


@pytest.mark.parametrize(
    "name",
    [
        "CTGOV_MAX_CONCURRENCY",
        "CTGOV_RATE_LIMIT_PER_MIN",
        "CTGOV_RATE_BURST",
        "SYNC_MAX_SECONDS",
        "MIRROR_SYNC_RATE_PER_MIN",
    ],
)
def test_limits_must_be_positive(make_settings, name: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{name: "0"})


def test_pricing_file_has_the_verified_prices() -> None:
    pricing = load_pricing()
    assert pricing.last_verified.isoformat() == "2026-10-24"
    mini = pricing.models["gpt-5.4-mini"]
    assert (mini.input, mini.cached_input, mini.output) == (0.75, 0.075, 4.50)
    assert "gpt-4o-2024-08-06" not in pricing.models


def test_every_default_model_has_a_price(make_settings) -> None:
    assert missing_prices(make_settings(), load_pricing()) == set()


def test_models_without_a_price_are_reported(make_settings) -> None:
    s = make_settings(PLANNER_MODEL="gpt-4o-2024-08-06")
    assert missing_prices(s, load_pricing()) == {"gpt-4o-2024-08-06"}
