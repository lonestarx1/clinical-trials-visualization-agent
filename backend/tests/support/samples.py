"""Real study records saved during the live API probe (docs/api/probe-data/samples)."""

import json
from functools import cache
from pathlib import Path
from typing import Any

SAMPLES_DIR = Path(__file__).resolve().parents[3] / "docs" / "api" / "probe-data" / "samples"


@cache
def sample_names() -> tuple[str, ...]:
    """Sample names, e.g. 'multi_phase' for multi_phase_NCT03724851.json."""
    return tuple(sorted(p.stem.rsplit("_", 1)[0] for p in SAMPLES_DIR.glob("*.json")))


def load_sample(name: str) -> dict[str, Any]:
    """Load one sample study by name. Returns a fresh copy each call."""
    matches = list(SAMPLES_DIR.glob(f"{name}_NCT*.json"))
    if len(matches) != 1:
        raise KeyError(f"no unique sample named {name!r} in {SAMPLES_DIR}")
    return json.loads(matches[0].read_text())
