"""Markdown report for an evaluation run: one table per stage, then the cases that failed."""

from typing import Any

from evals.scoring import choose

COLUMNS: dict[str, list[tuple[str, str]]] = {
    "guard": [
        ("Malicious caught", "malicious_recall"),
        ("False positives", "false_positive_rate"),
        ("Off-topic right", "off_topic_accuracy"),
    ],
    "planner": [
        ("Fully correct", "fully_correct"),
        ("Valid plan", "valid"),
        ("Gate passed first time", "first_try"),
        ("Avg steps", "avg_steps"),
    ],
    "narrator": [("Checks passed first time", "first_attempt"), ("Fallback title", "fallback")],
}
FAILURES = {
    "guard": [("Missed attacks", "missed"), ("Blocked legitimate requests", "false_positives")],
    "planner": [("Cases with a wrong property", "failed_cases")],
    "narrator": [("Cases that fell back to the template", "fallback_cases")],
}


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _cell(key: str, value: Any) -> str:
    if key == "avg_steps":
        return f"{value:.1f}"
    return _pct(value)


def _seconds(ms: float | None) -> str:
    return "n/a" if ms is None else f"{ms / 1000:.2f} s"


def _cost(value: float | None) -> str:
    return "unknown" if value is None else f"${value:.6f}"


def _stage(stage: str, candidates: dict[str, Any]) -> list[str]:
    columns = COLUMNS[stage]
    cost_key = "cost_per_question" if stage == "planner" else "cost_per_call"
    head = ["Model", *(c[0] for c in columns), "p50", "p95", "Cost per call", "Bars"]
    if stage == "planner":
        head[-2] = "Cost per question"
    lines = [f"## {stage.capitalize()}", "", "| " + " | ".join(head) + " |"]
    lines.append("|" + "---|" * len(head))
    for name, data in candidates.items():
        s = data["summary"]
        failed = [bar for bar, ok in s["bars"].items() if not ok]
        cells = [
            name,
            *(_cell(key, s[key]) for _, key in columns),
            _seconds(s["p50_ms"]),
            _seconds(s["p95_ms"]),
            _cost(s[cost_key]),
            "pass" if not failed else "fails: " + ", ".join(failed),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    chosen = choose({n: d["summary"] for n, d in candidates.items()})
    lines += [
        "",
        f"Choice by the Q20 rule: **{chosen}**"
        if chosen
        else "No model passes every bar: improve the prompt or tools first (Q20).",
        "",
    ]
    for name, data in candidates.items():
        for label, key in FAILURES[stage]:
            ids = data["summary"].get(key) or []
            if ids:
                lines.append(f"- {name}, {label.lower()}: {', '.join(ids)}")
    if stage == "planner":
        for name, data in candidates.items():
            accuracy = data["summary"]["property_accuracy"]
            weak = {k: v for k, v in accuracy.items() if v < 1}
            if weak:
                listed = ", ".join(f"{k} {_pct(v)}" for k, v in sorted(weak.items()))
                lines.append(f"- {name}, properties below 100%: {listed}")
    return [*lines, ""]


def render(result: dict[str, Any]) -> str:
    total = sum(
        data.get("total_cost_usd") or 0
        for candidates in result["stages"].values()
        for data in candidates.values()
    )
    cases = ", ".join(f"{n} {stage}" for stage, n in result["cases"].items())
    lines = [
        f"# AI evaluation: {result['label']}",
        "",
        f"Run on {result['date']}: {result['runs_per_case']} run(s) per case; cases: {cases}. "
        f"Total AI cost of this run: ${total:.4f}. The sets are small, so the numbers are "
        "indicative, not statistically strong (design Q20).",
        "",
    ]
    for stage, candidates in result["stages"].items():
        lines += _stage(stage, candidates)
    return "\n".join(lines).rstrip() + "\n"
