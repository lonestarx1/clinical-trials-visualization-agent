"""Typed settings from environment variables / .env, validated at startup (design Q19, Q20)."""

from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveFloat,
    PositiveInt,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

ReasoningEffort = Literal["minimal", "low", "medium", "high"]


class StageSettings(BaseModel):
    """Model settings for one AI stage, read from <STAGE>_* env vars (e.g. PLANNER_MODEL)."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    fallback_model: str | None = "gpt-4.1-mini"
    reasoning_effort: ReasoningEffort = "low"
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: PositiveInt
    timeout_seconds: PositiveFloat
    max_retries: int = Field(default=2, ge=0, le=5)

    @field_validator("fallback_model", mode="before")
    @classmethod
    def _empty_disables_fallback(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def _fallback_differs(self) -> Self:
        if self.fallback_model == self.model:
            raise ValueError(f"fallback_model must differ from model ({self.model})")
        return self


class PlannerSettings(StageSettings):
    max_steps: PositiveInt = 6


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        env_nested_delimiter="_",
        env_nested_max_split=1,
        nested_model_default_partial_update=True,
        extra="ignore",
    )

    openai_api_key: SecretStr
    database_url: str = "postgresql+asyncpg://ctviz:ctviz@localhost:5432/ctviz"
    ctgov_base_url: str = "https://clinicaltrials.gov/api/v2"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]
    enable_debug_endpoints: bool = True

    guard: StageSettings = StageSettings(
        model="gpt-5.4-nano", max_output_tokens=1000, timeout_seconds=5
    )
    planner: PlannerSettings = PlannerSettings(
        model="gpt-5.4-mini", max_output_tokens=4000, timeout_seconds=30
    )
    narrator: StageSettings = StageSettings(
        model="gpt-5.4-nano", max_output_tokens=1000, timeout_seconds=10
    )
    llm_startup_ping: bool = False

    rate_limit_per_ip_per_min: PositiveInt = 300
    max_active_jobs_per_ip: PositiveInt = 10
    llm_daily_budget_usd: PositiveFloat = 100
    ctgov_rate_limit_per_min: PositiveInt = 40
    ctgov_max_concurrency: PositiveInt = 2
    sync_max_seconds: PositiveInt = 60
    citations_full_max: PositiveInt = 2000

    @field_validator("openai_api_key")
    @classmethod
    def _key_not_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("OPENAI_API_KEY is required")
        return value

    def configured_models(self) -> set[str]:
        stages = (self.guard, self.planner, self.narrator)
        return {m for s in stages for m in (s.model, s.fallback_model) if m}
