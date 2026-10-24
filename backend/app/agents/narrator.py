"""Narrator (design Q4b V5-V9): the AI writes the title and summary, code supplies the numbers.

The model sees only a fact sheet computed from the chart and writes with
{placeholders}; code fills them in, so numbers are correct by construction.
The rendered text is then checked (numbers, names, banned claims, length).
After one failed retry, the deterministic template from the chart builder is used.
"""

import json
import logging
import re
import statistics
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ctgov.countries import CANONICAL as COUNTRIES
from app.llm.client import LLM, LLMUnavailable
from app.pipeline.aggregate import NOT_REPORTED_LABEL
from app.pipeline.charts import ChartMeta, measure_text
from app.registry import DIMENSIONS, ChartType
from app.registry.enums import Phase, Status
from app.schemas.plan import QueryPlan
from app.schemas.response import Visualization

log = logging.getLogger(__name__)

TITLE_MAX, SUMMARY_MAX = 90, 200
BANNED = [
    "effective",
    "effectiveness",
    "efficacy",
    "efficacious",
    "best",
    "worst",
    "safe",
    "safer",
    "safest",
    "unsafe",
    "proves",
    "proven",
    "prove",
    "cure",
    "cures",
    "cured",
    "superior",
    "inferior",
    "better",
    "worse",
    "breakthrough",
    "promising",
    "successful",
    "recommend",
    "recommended",
]
_BANNED = re.compile(r"\b(" + "|".join(BANNED) + r")\b", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# Names the text must not mention unless they are in the chart or the filters (V7).
_VOCABULARY = (
    [p.label for p in Phase] + [s.label for s in Status if " " in s.label] + list(COUNTRIES)
)

INSTRUCTIONS = f"""You write the title and a one-sentence summary for a chart of \
ClinicalTrials.gov data.

Rules:
- Use {{placeholders}} for every number and count, written exactly as {{fact_name}} with a \
name from "facts" (e.g. {{total}}, {{max_value}}). Never type a number yourself.
- Summarise the main pattern (e.g. the largest category, or the trend); don't list every \
category.
- Only mention categories that appear in the chart labels or the facts.
- Describe what the chart shows. No judgements about drugs, treatments or sponsors, and no \
medical conclusions (never words like "effective", "safe", "best", "promising").
- Title: at most {TITLE_MAX} characters; don't start it with "ClinicalTrials.gov".
- Summary: one sentence, at most {SUMMARY_MAX} characters.
- Return JSON: {{"title": "...", "summary": "..."}}."""

SCHEMA = {
    "name": "narration",
    "schema": {
        "type": "object",
        "properties": {"title": {"type": "string"}, "summary": {"type": "string"}},
        "required": ["title", "summary"],
        "additionalProperties": False,
    },
}


class _Text(BaseModel):
    title: str
    summary: str


@dataclass
class Narration:
    title: str
    summary: str
    model: str | None
    attempts: int
    fallback: bool
    errors: list[str] = field(default_factory=list)


def _fmt(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"


def _scope(plan: QueryPlan) -> str:
    f = plan.filters
    terms = [*f.drugs, *f.conditions, *f.sponsors, *f.countries]
    if plan.groups:
        terms.append(" vs ".join(g.label for g in plan.groups))
    return ", ".join(terms) or "all trials"


def _labels(plan: QueryPlan, viz: Visualization) -> list[str]:
    if isinstance(viz.data, dict):  # network
        return [str(n["label"]) for n in viz.data["nodes"]]
    if not plan.dimension:
        return []
    key = plan.dimension if viz.type is not ChartType.HISTOGRAM else "key"
    return [str(r[key]) for r in viz.data if key in r]


_SOURCE_PREFIX = re.compile(r"^\s*clinicaltrials\.gov\s*[:\-\u2013]?\s*", re.IGNORECASE)


def _without_source(title: str) -> str:
    """Every chart comes from ClinicalTrials.gov, so a title doesn't need to say so."""
    stripped = _SOURCE_PREFIX.sub("", title)
    return stripped[:1].upper() + stripped[1:] if stripped else title


def fact_sheet(plan: QueryPlan, viz: Visualization, meta: ChartMeta) -> dict[str, str]:
    facts = {
        "total": _fmt(meta.unique_trials),
        "measure": measure_text(plan)[0].lower(),
        "dimension": DIMENSIONS[plan.dimension].label.lower() if plan.dimension else "",
        "scope": _scope(plan),
    }
    if plan.measure == "distinct_count":
        facts["entity"] = measure_text(plan)[1]
        facts["min_trials"] = str(plan.options.min_trials or 1)
    if isinstance(viz.data, dict):  # network
        nodes, edges = viz.data["nodes"], viz.data["edges"]
        names = {n["id"]: n["label"] for n in nodes}
        facts |= {"n_nodes": _fmt(len(nodes)), "n_edges": _fmt(len(edges))}
        if nodes:
            hub = max(nodes, key=lambda n: (n["degree"], n["weight"]))
            facts |= {
                "top_node": hub["label"],
                "top_node_degree": _fmt(hub["degree"]),
                "top_node_trials": _fmt(hub["weight"]),
            }
        if edges:
            strongest = edges[0]  # sorted by weight
            facts |= {
                "strongest_link": f"{names[strongest['source']]} - {names[strongest['target']]}",
                "strongest_link_trials": _fmt(strongest["weight"]),
            }
        return facts
    if viz.type is ChartType.SCATTER_PLOT:
        assert plan.dimension and plan.dimension_2
        points = viz.data if isinstance(viz.data, list) else []
        xs = [p[plan.dimension] for p in points]
        ys = [p[plan.dimension_2] for p in points]
        facts["n_points"] = _fmt(len(xs))
        if xs:
            facts |= {
                "median_x": _fmt(statistics.median(xs)),
                "median_y": _fmt(statistics.median(ys)),
                "x_label": DIMENSIONS[plan.dimension].label.lower(),
                "y_label": DIMENSIONS[plan.dimension_2].label.lower(),
            }
        return facts
    if viz.type is ChartType.METRIC:
        facts["value"] = _fmt(viz.data[0]["value"])
        return facts
    if viz.type is ChartType.HISTOGRAM:
        largest = max(viz.data, key=lambda r: r["count"])
        facts |= {
            "largest_bin": largest["key"],
            "largest_bin_count": _fmt(largest["count"]),
            "n_bins": _fmt(len(viz.data)),
        }
        return facts

    assert plan.dimension is not None
    value_key, label_key = plan.measure, plan.dimension
    rows = [r for r in viz.data if r[label_key] != NOT_REPORTED_LABEL]
    if not rows:
        return facts
    top = max(rows, key=lambda r: r[value_key])
    low = min(rows, key=lambda r: r[value_key])
    ranked = sorted(rows, key=lambda r: -r[value_key])
    facts |= {
        "n_buckets": _fmt(len({r[label_key] for r in rows})),
        "max_bucket": str(top[label_key]),
        "max_value": _fmt(top[value_key]),
        "min_bucket": str(low[label_key]),
        "min_value": _fmt(low[value_key]),
        "next_items": ", ".join(
            [x for x in dict.fromkeys(str(r[label_key]) for r in ranked) if x != top[label_key]][:3]
        ),
    }
    if "group" in top:
        facts["max_group"] = str(top["group"])
        for i, g in enumerate(plan.groups, start=1):
            facts[f"group_{i}"] = g.label
    if meta.additive and plan.measure == "trial_count" and meta.unique_trials and not plan.groups:
        facts["share_of_max"] = f"{round(100 * top[value_key] / meta.unique_trials)}%"
    if viz.type is ChartType.TIME_SERIES:
        facts["first_bucket"], facts["last_bucket"] = (
            str(rows[0][label_key]),
            str(rows[-1][label_key]),
        )
        values = [r[value_key] for r in rows]
        head, tail = values[: max(len(values) // 3, 1)], values[-max(len(values) // 3, 1) :]
        start, end = sum(head) / len(head), sum(tail) / len(tail)
        facts["trend_direction"] = (
            "increased"
            if end > start * 1.1
            else "decreased"
            if end < start * 0.9
            else "stayed roughly flat"
        )
    return facts


def render(template: str, facts: dict[str, str]) -> str:
    return _PLACEHOLDER.sub(lambda m: facts[m.group(1)], template)


def check_text(
    template: str, facts: dict[str, str], plan: QueryPlan, viz: Visualization, *, max_length: int
) -> list[str]:
    unknown = [n for n in _PLACEHOLDER.findall(template) if n not in facts]
    if unknown:
        return [f"unknown placeholder {{{n}}}" for n in unknown]
    text = render(template, facts)
    if "{" in text or "}" in text:
        return [f"malformed placeholder in {template!r}: use {{name}} with a fact name only"]
    errors = []
    if len(text) > max_length:
        errors.append(f"too long ({len(text)} > {max_length} characters)")

    allowed = [
        *_labels(plan, viz),
        *(g.label for g in plan.groups),
        facts["scope"],
        *(str(v) for v in facts.values()),
    ]
    allowed_lower = " | ".join(a.lower() for a in allowed)
    for name in _VOCABULARY:  # V7
        if (
            re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE)
            and name.lower() not in allowed_lower
        ):
            errors.append(f"'{name}' is not in the chart")

    literal = _PLACEHOLDER.sub(" ", template)  # V6: numbers typed by the model
    for name in sorted([*allowed, *_VOCABULARY], key=len, reverse=True):
        if name:
            literal = re.sub(re.escape(name), " ", literal, flags=re.IGNORECASE)
    known = {v.replace(",", "").rstrip("%") for v in facts.values()}
    for number in _NUMBER.findall(literal):
        if number.replace(",", "") not in known:
            errors.append(f"number {number} is not a fact; use a placeholder")

    errors += [f"banned word '{m.lower()}'" for m in _BANNED.findall(text)]  # V8
    words = re.findall(r"\w+", text.lower())
    seen: set[tuple[str, ...]] = set()
    for i in range(len(words) - 2):  # e.g. a placeholder wrapped in its own words
        trigram = tuple(words[i : i + 3])
        if trigram in seen:
            errors.append(f"repeats '{' '.join(trigram)}': check how placeholders read")
            break
        seen.add(trigram)
    return errors


async def narrate(
    llm: LLM, plan: QueryPlan, viz: Visualization, meta: ChartMeta, attempts: int = 2
) -> Narration:
    facts = fact_sheet(plan, viz, meta)
    brief = {
        "chart_type": viz.type,
        "dimension": facts["dimension"],
        "measure": facts["measure"],
        "chart_labels": _labels(plan, viz)[:30],
        "facts": facts,
    }
    items: list[dict[str, Any]] = [
        {"role": "user", "content": json.dumps(brief, ensure_ascii=False)}
    ]
    errors: list[str] = []
    model = None
    for attempt in range(1, attempts + 1):
        try:
            reply = await llm.respond(items, json_schema=SCHEMA, instructions=INSTRUCTIONS)
        except LLMUnavailable as exc:
            errors.append(f"model unavailable: {exc}")
            break
        model = reply.model
        try:
            out = _Text.model_validate_json(reply.text)
        except ValidationError:
            errors = ["the reply was not the requested JSON"]
        else:
            errors = check_text(out.title, facts, plan, viz, max_length=TITLE_MAX)
            errors += check_text(out.summary, facts, plan, viz, max_length=SUMMARY_MAX)
            if not errors:
                title = _without_source(render(out.title, facts))
                return Narration(title, render(out.summary, facts), model, attempt, False)
        items += reply.output_items
        items.append(
            {"role": "user", "content": "Fix these problems and answer again: " + "; ".join(errors)}
        )
        log.info("narration attempt %d failed: %s", attempt, errors)
    return Narration(viz.title, viz.summary, model, attempt, True, errors)
