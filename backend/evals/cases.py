"""The evaluation cases (design Q18), kept as YAML next to this file.

- planner.yaml: questions with the plan properties a correct plan has. A value can be
  `{any_of: [...]}` when more than one reading is right.
- guard.yaml: requests labelled ok, off_topic or malicious.
- narrator.yaml: plans whose live results give the narrator real fact sheets.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CASES_DIR = Path(__file__).parent / "cases"
EXPECT_KEYS = {
    "scope",
    "intent",
    "chart_type",
    "dimension",
    "dimension_2",
    "measure",
    "filters",
    "options",
    "groups",
    "has_suggestion",
    "extra_filters_ok",
}


@dataclass(frozen=True)
class PlannerCase:
    id: str
    request: dict[str, Any]
    expect: dict[str, Any]


@dataclass(frozen=True)
class GuardCase:
    id: str
    request: dict[str, Any]
    expected: str


@dataclass(frozen=True)
class NarratorCase:
    id: str
    question: str
    plan: dict[str, Any]


def _load(name: str) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = yaml.safe_load((CASES_DIR / name).read_text())
    return data


def _request(raw: str | dict[str, Any]) -> dict[str, Any]:
    return {"query": raw} if isinstance(raw, str) else raw


def load_planner_cases() -> list[PlannerCase]:
    return [
        PlannerCase(c["id"], _request(c["request"]), c["expect"]) for c in _load("planner.yaml")
    ]


def load_guard_cases() -> list[GuardCase]:
    return [GuardCase(c["id"], _request(c["request"]), c["expected"]) for c in _load("guard.yaml")]


def load_narrator_cases() -> list[NarratorCase]:
    return [NarratorCase(c["id"], c["question"], c["plan"]) for c in _load("narrator.yaml")]
