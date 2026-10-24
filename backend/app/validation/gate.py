"""The plan gate (design Q3, Q4b V1/V2/V4, Q5): code re-checks every plan the agent submits.

Used twice: as the agent's `check_plan` / `submit_plan` tools (errors go back
to the agent), and as the final gate, where the agent's self-check is never
trusted alone.
"""

import copy
import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from app.registry import DIMENSIONS, ChartType, DimensionKind, Intent
from app.schemas.plan import QueryPlan
from app.schemas.request import QueryRequest

DEFAULT_CHART = {
    Intent.TREND: ChartType.TIME_SERIES,
    Intent.DISTRIBUTION: ChartType.BAR_CHART,
    Intent.TOP_N: ChartType.BAR_CHART,
    Intent.COMPARISON: ChartType.GROUPED_BAR_CHART,
    Intent.GEOGRAPHIC: ChartType.BAR_CHART,
    Intent.NETWORK: ChartType.NETWORK_GRAPH,
    Intent.NUMERIC_DISTRIBUTION: ChartType.HISTOGRAM,
    Intent.NUMERIC_RELATIONSHIP: ChartType.SCATTER_PLOT,
    Intent.SINGLE_NUMBER: ChartType.METRIC,
}
NOT_BUILT_YET: set[ChartType] = set()

ChartSource = Literal["ai", "user", "fallback"]


@dataclass
class GateResult:
    plan: QueryPlan | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    chart_type_source: ChartSource = "ai"


def default_chart(intent: str) -> ChartType:
    return DEFAULT_CHART[Intent(intent)]


# ---------- V1: chart compatibility (Q3) ----------


def compatibility_errors(plan: QueryPlan) -> list[str]:
    chart = plan.chart_type
    dim = DIMENSIONS[plan.dimension] if plan.dimension else None
    kind = dim.kind if dim else None
    if chart in NOT_BUILT_YET:
        return [f"{chart} is not available yet; choose another chart type."]
    if plan.measure == "distinct_count":
        if chart in (ChartType.HISTOGRAM, ChartType.SCATTER_PLOT, ChartType.NETWORK_GRAPH):
            return [
                f"distinct_count can't be shown as {chart}; use bar_chart, grouped_bar_chart, "
                "time_series or metric."
            ]
        if plan.dimension and plan.dimension in (plan.options.count_entity, plan.dimension_2):
            return ["distinct_count: count_entity must differ from the dimension."]
    if chart is ChartType.METRIC:
        return ["metric takes no dimension."] if dim else []
    if dim is None:
        return [f"{chart} needs a dimension."]
    dim_2 = DIMENSIONS[plan.dimension_2] if plan.dimension_2 else None
    if chart is ChartType.NETWORK_GRAPH:
        kinds = {kind, dim_2.kind if dim_2 else kind}
        errors = (
            []
            if kinds == {DimensionKind.ENTITY}
            else [
                "network_graph needs entity dimensions (e.g. drug alone for co-occurrence, or "
                "sponsor + drug)."
            ]
        )
        return errors + (["network_graph can't show comparison groups."] if plan.groups else [])
    if chart is ChartType.SCATTER_PLOT:
        if (
            kind is not DimensionKind.NUMERIC
            or not dim_2
            or dim_2.kind is not DimensionKind.NUMERIC
        ):
            return ["scatter_plot needs two numeric dimensions (dimension and dimension_2)."]
        return ["scatter_plot can't show comparison groups."] if plan.groups else []
    errors = []
    if chart is ChartType.TIME_SERIES and kind is not DimensionKind.TIME:
        errors.append("time_series needs a time dimension (start_year or first_posted_year).")
    if chart is ChartType.HISTOGRAM and kind is not DimensionKind.NUMERIC:
        errors.append(
            "histogram needs a numeric dimension (enrollment, duration_months, site_count)."
        )
    if chart in (ChartType.BAR_CHART, ChartType.GROUPED_BAR_CHART) and kind not in (
        DimensionKind.CATEGORICAL,
        DimensionKind.ENTITY,
    ):
        errors.append(f"{chart} needs a categorical or entity dimension.")
    if chart is ChartType.GROUPED_BAR_CHART and not plan.groups and not dim_2:
        errors.append(
            "grouped_bar_chart needs comparison groups (2-4) or a dimension_2 to split by."
        )
    if dim_2 and dim_2.kind not in (DimensionKind.CATEGORICAL, DimensionKind.ENTITY):
        errors.append("dimension_2 (series split) must be a categorical or entity dimension.")
    if dim_2 and plan.groups:
        errors.append("Use either comparison groups or dimension_2, not both.")
    if dim_2 and chart is ChartType.BAR_CHART:
        errors.append("A split by dimension_2 needs grouped_bar_chart.")
    if chart in (ChartType.BAR_CHART, ChartType.HISTOGRAM, ChartType.METRIC) and plan.groups:
        errors.append(
            f"{chart} can't show comparison groups; use grouped_bar_chart or time_series."
        )
    return errors


# ---------- merging request fields (Q5) ----------

_ENTITY_FIELDS = {
    "drug_name": "drugs",
    "condition": "conditions",
    "sponsor": "sponsors",
    "country": "countries",
}
_OPTION_FIELDS = (
    "top_n",
    "phase_mode",
    "condition_source",
    "include_unknown",
    "edge_metric",
    "hide_query_entity",
)


def _merge_fields(
    raw: dict[str, Any], request: QueryRequest
) -> tuple[dict[str, Any], list[str], bool]:
    """Structured fields override the AI's plan. Returns (plan, warnings, chart type from user)."""
    plan = copy.deepcopy(raw)
    filters = plan.setdefault("filters", {}) or {}
    plan["filters"] = filters
    given = request.model_fields_set
    warnings = []

    for name, key in _ENTITY_FIELDS.items():
        values = getattr(request, name)
        if name in given and values:
            old = filters.get(key) or []
            if old and [_norm(v) for v in old] != [_norm(v) for v in values]:
                warnings.append(
                    f"The {name} field ({', '.join(values)}) overrides "
                    f"the question's {', '.join(old)}."
                )
            filters[key] = list(values)
    if "trial_phase" in given:
        filters["phases"] = [p.value for p in request.trial_phase]
    if "status" in given:
        filters["statuses"] = [s.value for s in request.status]
    if "start_year" in given:
        filters["start_year_min"] = request.start_year
    if "end_year" in given:
        filters["start_year_max"] = request.end_year
    for name in ("match_mode", "sponsor_role"):
        if name in given:
            filters[name] = getattr(request, name)
    if request.compare:
        plan["groups"] = [
            {
                "label": g.label,
                "filters": {
                    key: getattr(g, name)
                    for name, key in _ENTITY_FIELDS.items()
                    if getattr(g, name)
                },
            }
            for g in request.compare
        ]
    options = plan.setdefault("options", {}) or {}
    plan["options"] = options
    for name in _OPTION_FIELDS:
        if name in given:
            options[name] = getattr(request, name)
    user_chart = request.chart_type is not None
    if user_chart:
        plan["chart_type"] = request.chart_type
    return plan, warnings, user_chart


# ---------- V2: entity grounding ----------


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def _grounded(term: str, source: str) -> bool:
    t, words = _norm(term), _norm(source).split()
    if not t:
        return True
    if f" {t} " in f" {' '.join(words)} ":
        return True
    n = len(t.split())
    for size in {max(n - 1, 1), n, n + 1}:
        for i in range(len(words) - size + 1):
            if difflib.SequenceMatcher(None, t, " ".join(words[i : i + size])).ratio() >= 0.85:
                return True
    return False


def _grounding_errors(plan: QueryPlan, request: QueryRequest) -> list[str]:
    sources = [request.query]
    for name in _ENTITY_FIELDS:
        sources += getattr(request, name)
    for g in request.compare:
        sources += [g.label, *g.drug_name, *g.condition, *g.sponsor, *g.country]
    source = " | ".join(sources)
    errors = []
    for filters in [plan.filters, *(g.filters for g in plan.groups)]:
        for term in [
            *filters.drugs,
            *filters.conditions,
            *filters.sponsors,
            *filters.countries,
            *filters.us_states,
        ]:
            if not _grounded(term, source):
                errors.append(
                    f"'{term}' does not appear in the question or fields. Use the user's own "
                    "words; ClinicalTrials.gov resolves synonyms itself."
                )
    return errors


# ---------- V4: unrequested filters need a reason ----------


def _mentioned(labels: list[str], query: str) -> bool:
    q = f" {_norm(query)} "
    return all(
        any(f" {variant} " in q or variant in q for variant in _variants(lbl)) for lbl in labels
    )


def _variants(label: str) -> list[str]:
    n = _norm(label)
    out = [n, n.replace(" ", "")]
    roman = {"1": "i", "2": "ii", "3": "iii", "4": "iv"}
    if n.startswith("phase ") and n[-1] in roman:
        out.append(f"phase {roman[n[-1]]}")
    return out


def _unrequested(plan: QueryPlan, request: QueryRequest) -> list[str]:
    f, given, query = plan.filters, request.model_fields_set, request.query
    found = []
    for key, values in (
        ("statuses", f.statuses),
        ("phases", f.phases),
        ("study_types", f.study_types),
        ("sponsor_classes", f.sponsor_classes),
        ("age_groups", f.age_groups),
        ("sexes", f.sexes),
        ("allocations", f.allocations),
        ("maskings", f.maskings),
        ("primary_purposes", f.primary_purposes),
    ):
        field_name = {"statuses": "status", "phases": "trial_phase"}.get(key)
        if values and field_name not in given and not _mentioned([v.label for v in values], query):
            found.append(key)
    for key, year, field_name in (
        ("start_year_min", f.start_year_min, "start_year"),
        ("start_year_max", f.start_year_max, "end_year"),
    ):
        if year is not None and field_name not in given and str(year) not in query:
            found.append(key)
    for key, flag in (("healthy_volunteers", f.healthy_volunteers), ("has_results", f.has_results)):
        if flag is not None and not _mentioned([key.replace("_", " ")], query):
            found.append(key)
    return found


# ---------- the plan must count what the question counts ----------

_ENTITY_WORDS = {
    "sponsor": "sponsors|companies",
    "collaborator": "collaborators",
    "drug": "drugs",
    "condition": "conditions|diseases",
    "country": "countries",
    "site": "sites|hospitals",
    "investigator": "investigators",
}
_COUNTED = {
    entity: re.compile(
        r"\b(?:number of|how many|count of|count the)\s+(?:distinct\s+|unique\s+|different\s+)?"
        rf"(?:lead\s+)?(?:{words})\b",
        re.IGNORECASE,
    )
    for entity, words in _ENTITY_WORDS.items()
}


def _measure_mismatch(plan: QueryPlan, request: QueryRequest) -> list[str]:
    """A question that counts entities ("how many sponsors") needs a plan that counts them."""
    errors = []
    for entity, pattern in _COUNTED.items():
        if not pattern.search(request.query):
            continue
        counted = plan.measure == "distinct_count" and plan.options.count_entity == entity
        if counted or plan.dimension == entity:
            continue
        errors.append(
            f"The question counts {entity}s, but the plan counts {plan.measure}. Use measure "
            f"distinct_count with options.count_entity={entity} (and options.min_trials for "
            '"more than N trials"), or set scope out_of_scope with the reason.'
        )
    return errors


# ---------- the gate ----------


def _readable(exc: ValidationError) -> list[str]:
    return [
        f"{'.'.join(str(p) for p in err['loc']) or 'plan'}: {err['msg']}" for err in exc.errors()
    ]


def check_plan(raw: dict[str, Any], request: QueryRequest, *, final: bool = False) -> GateResult:
    merged, warnings, user_chart = _merge_fields(raw, request)
    try:
        plan = QueryPlan.model_validate(merged)
    except ValidationError as exc:
        return GateResult(None, _readable(exc), warnings)

    result = GateResult(plan, [], warnings, "user" if user_chart else "ai")
    if plan.scope == "out_of_scope":
        return result

    compat = compatibility_errors(plan)
    if compat and final and not user_chart:
        fallback = plan.model_copy(update={"chart_type": default_chart(plan.intent)})
        if not compatibility_errors(fallback):
            warnings.append(
                f"Chart type {plan.chart_type} doesn't fit this question; "
                f"using {fallback.chart_type}."
            )
            plan, compat = fallback, []
            result.plan, result.chart_type_source = plan, "fallback"
    result.errors += compat
    result.errors += _grounding_errors(plan, request)
    result.errors += _measure_mismatch(plan, request)

    unrequested = _unrequested(plan, request)
    if unrequested and not plan.assumptions:
        result.errors.append(
            f"Filters not asked for in the question: {', '.join(unrequested)}. Remove them, or "
            "explain each one in assumptions."
        )
    if result.errors:
        result.plan = None
    return result
