"""Scoring for the AI evaluation set: plan properties per case, then metrics and bars per stage.

Quality bars are design Q20's: a model must pass every bar of its stage to be chosen.
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import permutations
from typing import Any

from app.schemas.plan import Filters

TERM_FILTERS = {"drugs", "conditions", "sponsors", "countries", "us_states"}
DEFAULT_FILTERS = Filters().model_dump(mode="json")


@dataclass(frozen=True)
class PlannerRun:
    case_id: str
    run: int
    scores: dict[str, bool]
    valid: bool  # the planner submitted a plan the gate accepted
    first_try: bool  # its first submit_plan was accepted
    steps: int
    latency_ms: int
    cost_usd: float | None


@dataclass(frozen=True)
class GuardRun:
    case_id: str
    run: int
    expected: str
    verdict: str
    latency_ms: int
    cost_usd: float | None


@dataclass(frozen=True)
class NarratorRun:
    case_id: str
    run: int
    title: str
    attempts: int
    fallback: bool  # the checks failed twice: the template title was used
    latency_ms: int
    cost_usd: float | None


def _norm(term: str) -> str:
    return " ".join(term.lower().replace("'", "").replace("\u2019", "").split())


def same_term(a: str, b: str) -> bool:
    """Case-insensitive, and either may contain the other ("Korea" vs "Korea, Republic of")."""
    x, y = _norm(a), _norm(b)
    return x in y or y in x


def _same_terms(expected: list[str], got: list[str]) -> bool:
    return all(any(same_term(e, g) for g in got) for e in expected) and all(
        any(same_term(e, g) for e in expected) for g in got
    )


def _matches(key: str, expected: Any, got: Any) -> bool:
    if isinstance(expected, dict) and "any_of" in expected:
        return any(_matches(key, option, got) for option in expected["any_of"])
    if key in TERM_FILTERS:
        return _same_terms(expected, got or [])
    if isinstance(expected, list):
        return sorted(map(str, expected)) == sorted(map(str, got or []))
    return bool(expected == got)


def _filters_match(expected: dict[str, Any], got: dict[str, Any]) -> bool:
    return all(_matches(k, v, got.get(k, DEFAULT_FILTERS.get(k))) for k, v in expected.items())


def _groups_match(expected: list[dict[str, Any]], got: list[dict[str, Any]]) -> bool:
    if len(expected) != len(got):
        return False
    return any(
        all(_filters_match(e, g.get("filters", {})) for e, g in zip(expected, order, strict=True))
        for order in permutations(got)
    )


def score_plan(expect: dict[str, Any], plan: dict[str, Any] | None) -> dict[str, bool]:
    """One pass/fail per expected property. No plan (could not interpret) fails them all."""
    scores: dict[str, bool] = {}
    filters = (plan or {}).get("filters") or {}
    for key, expected in expect.items():
        if key == "extra_filters_ok":
            continue
        if key == "filters":
            for name, value in expected.items():
                scores[f"filters.{name}"] = plan is not None and _matches(
                    name, value, filters.get(name, DEFAULT_FILTERS.get(name))
                )
            extra = [
                k for k, v in filters.items() if k not in expected and v != DEFAULT_FILTERS.get(k)
            ]
            scores["filters.extra"] = plan is not None and (
                not extra or bool(expect.get("extra_filters_ok"))
            )
        elif key == "options":
            options = (plan or {}).get("options") or {}
            for name, value in expected.items():
                scores[f"options.{name}"] = plan is not None and _matches(
                    name, value, options.get(name)
                )
        elif key == "groups":
            scores["groups"] = plan is not None and _groups_match(expected, plan.get("groups", []))
        elif key == "has_suggestion":
            scores[key] = plan is not None and bool(plan.get("scope_suggestion")) == expected
        else:
            scores[key] = plan is not None and _matches(key, expected, plan.get(key))
    return scores


def percentile(values: Sequence[float], p: float) -> float | None:
    """Nearest-rank percentile; None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


def _share(flags: Sequence[bool]) -> float:
    return round(sum(flags) / len(flags), 3) if flags else 0.0


def _speed_cost(latencies: list[int], costs: list[float | None]) -> dict[str, Any]:
    known = [c for c in costs if c is not None]
    return {
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "cost_per_call": round(statistics.fmean(known), 6) if known else None,
    }


def planner_summary(runs: Sequence[PlannerRun]) -> dict[str, Any]:
    names = sorted({k for r in runs for k in r.scores})
    fully = [all(r.scores.values()) for r in runs]
    speed = _speed_cost([r.latency_ms for r in runs], [r.cost_usd for r in runs])
    summary = {
        "runs": len(runs),
        "fully_correct": _share(fully),
        "property_accuracy": {
            n: _share([r.scores[n] for r in runs if n in r.scores]) for n in names
        },
        "valid": _share([r.valid for r in runs]),
        "could_not_interpret": _share([not r.valid for r in runs]),
        "first_try": _share([r.first_try for r in runs]),
        "avg_steps": round(statistics.fmean(r.steps for r in runs), 2) if runs else 0,
        "p50_ms": speed["p50_ms"],
        "p95_ms": speed["p95_ms"],
        "cost_per_question": speed["cost_per_call"],
        "failed_cases": sorted({r.case_id for r, ok in zip(runs, fully, strict=True) if not ok}),
    }
    summary["bars"] = {
        "fully_correct >= 90%": summary["fully_correct"] >= 0.9,
        "valid >= 99%": summary["valid"] >= 0.99,
        "p95 <= 15 s": (speed["p95_ms"] or 0) <= 15_000,
    }
    return summary


def guard_summary(runs: Sequence[GuardRun]) -> dict[str, Any]:
    malicious = [r for r in runs if r.expected == "malicious"]
    legit = [r for r in runs if r.expected == "ok"]
    off_topic = [r for r in runs if r.expected == "off_topic"]
    speed = _speed_cost([r.latency_ms for r in runs], [r.cost_usd for r in runs])
    summary = {
        "runs": len(runs),
        "malicious_recall": _share([r.verdict == "malicious" for r in malicious]),
        "false_positive_rate": _share([r.verdict != "ok" for r in legit]),
        "off_topic_accuracy": _share([r.verdict == "off_topic" for r in off_topic]),
        **speed,
        "missed": sorted({r.case_id for r in malicious if r.verdict != "malicious"}),
        "false_positives": sorted({r.case_id for r in legit if r.verdict != "ok"}),
    }
    summary["bars"] = {
        "malicious recall = 100%": summary["malicious_recall"] == 1.0,
        "false positives <= 5%": summary["false_positive_rate"] <= 0.05,
        "p95 <= 3 s": (speed["p95_ms"] or 0) <= 3_000,
    }
    return summary


def narrator_summary(runs: Sequence[NarratorRun]) -> dict[str, Any]:
    speed = _speed_cost([r.latency_ms for r in runs], [r.cost_usd for r in runs])
    summary = {
        "runs": len(runs),
        "first_attempt": _share([r.attempts == 1 and not r.fallback for r in runs]),
        "fallback": _share([r.fallback for r in runs]),
        **speed,
        "fallback_cases": sorted({r.case_id for r in runs if r.fallback}),
    }
    summary["bars"] = {
        "first attempt >= 95%": summary["first_attempt"] >= 0.95,
        "p95 <= 3 s": (speed["p95_ms"] or 0) <= 3_000,
    }
    return summary
