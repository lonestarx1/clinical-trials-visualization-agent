"""Model prices, used to record the cost of every LLM call (design Q16, Q20)."""

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, PositiveFloat

from app.core.config import Settings

PRICING_FILE = Path(__file__).with_name("pricing.yaml")


class ModelPrice(BaseModel):
    """USD per 1M tokens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input: PositiveFloat
    cached_input: PositiveFloat
    output: PositiveFloat


class Pricing(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    last_verified: date
    models: dict[str, ModelPrice]


def load_pricing(path: Path = PRICING_FILE) -> Pricing:
    return Pricing.model_validate(yaml.safe_load(path.read_text()))


def missing_prices(settings: Settings, pricing: Pricing) -> set[str]:
    """Configured models with no known price. Their cost is recorded as unknown, never $0."""
    return settings.configured_models() - pricing.models.keys()
