"""Grouped trials -> visualization spec + chart metadata (design Q3, Q9, Q10, Q12, Q14).

Titles and summaries here are templates. The narrator (M2) replaces them,
and falls back to these when its output fails the checks (Q4b).
"""

import math
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Literal

from app.pipeline.aggregate import NOT_REPORTED, Bucket, Grouping, group, nct_id, year_range
from app.pipeline.citations import sample_citations
from app.pipeline.extract import Evidence, extract_number
from app.pipeline.networks import build_network
from app.registry import DIMENSIONS, MEASURES, ChartType, Dimension, DimensionKind, Intent
from app.registry.enums import Phase
from app.schemas.plan import QueryPlan
from app.schemas.response import Channel, Excluded, Sort, Visualization

DEFAULT_TOP_N = 10
DEFAULT_BINS = 10
GroupedStudies = Sequence[tuple[str | None, Sequence[dict[str, Any]]]]


@dataclass
class ChartMeta:
    counting_rule: str
    additive: bool
    unique_trials: int
    excluded: list[Excluded] = field(default_factory=list)
    sort: Sort | None = None
    notes: list[str] = field(default_factory=list)
    group_overlap: list[dict[str, Any]] | None = None
    network: dict[str, Any] | None = None


@dataclass
class ChartResult:
    visualization: Visualization
    meta: ChartMeta


# ---------- measures ----------


@dataclass
class Measured:
    value: float
    evidence: dict[str, tuple[Evidence, ...]]  # contributing trials -> evidence


def _measure(bucket: Bucket, measure: str, studies: dict[str, dict[str, Any]]) -> Measured:
    if measure == "trial_count":
        return Measured(len(bucket.trials), dict(bucket.trials))
    numbers = {i: extract_number(studies[i], "enrollment") for i in bucket.trials}
    known = {i: n for i, n in numbers.items() if n is not None}
    values = [n.value for n in known.values()]
    if measure == "total_enrollment":
        total: float = sum(values)
    else:
        total = statistics.median(values) if values else 0
    total = int(total) if float(total).is_integer() else total
    return Measured(total, {i: bucket.trials[i] + known[i].evidence for i in known})


def _no_enrollment(trials: set[str], studies: dict[str, dict[str, Any]]) -> int:
    return sum(1 for i in trials if extract_number(studies[i], "enrollment") is None)


# ---------- ordering ----------


def _phase_rank(key: str) -> tuple[int, int]:
    order = [p.value for p in Phase if p is not Phase.NA]
    first = key.split("/")[0]
    if first in order:
        return (order.index(first), key.count("/"))
    return ({"NA": 100, "NO_PHASE": 101}.get(key, 102), 0)


def _natural_rank(dim: Dimension, key: str) -> tuple[int, int]:
    if dim.key == "phase":
        return _phase_rank(key)
    if dim.enum is not None and key in dim.enum._value2member_map_:
        return (list(dim.enum._value2member_map_).index(key), 0)
    return (999, 0)


def _sorted_keys(
    dim: Dimension, plan: QueryPlan, totals: dict[str, float], labels: dict[str, str]
) -> tuple[list[str], Sort, list[str]]:
    """Bucket order, the sort description, and notes (e.g. top-N truncation)."""
    real = [k for k in totals if k != NOT_REPORTED]
    tail = [NOT_REPORTED] if NOT_REPORTED in totals else []
    notes: list[str] = []
    if dim.kind is DimensionKind.TIME:
        return sorted(real, key=int) + tail, Sort(by="x", order="asc"), notes

    by_value = (
        dim.kind is DimensionKind.ENTITY
        or plan.options.top_n is not None
        or plan.intent in (Intent.TOP_N, Intent.GEOGRAPHIC)
    )
    if not by_value:
        return (
            sorted(real, key=lambda k: _natural_rank(dim, k)) + tail,
            Sort(by="x", order="natural"),
            notes,
        )

    ranked = sorted(real, key=lambda k: (-totals[k], labels[k].casefold()))
    limit = plan.options.top_n or (DEFAULT_TOP_N if dim.kind is DimensionKind.ENTITY else None)
    if limit is not None and len(ranked) > limit:
        notes.append(f"Showing the top {limit} of {len(ranked)} {_plural(dim)}.")
        ranked = ranked[:limit]
    return ranked + tail, Sort(by="y", order="desc"), notes


def _plural(dim: Dimension) -> str:
    word = dim.label.lower()
    return word[:-1] + "ies" if word.endswith("y") else word + "s"


# ---------- encodings ----------


def _x_channel(dim: Dimension, sort: Sort) -> Channel:
    if dim.kind is DimensionKind.TIME:
        return Channel(field=dim.key, type="temporal", label=dim.label, time_unit="year")
    kind: Literal["nominal", "ordinal"] = (
        "nominal" if dim.kind is DimensionKind.ENTITY else "ordinal"
    )
    order: Literal["natural", "descending", "ascending"] = (
        "natural"
        if sort.order == "natural"
        else "descending"
        if sort.order == "desc"
        else "ascending"
    )
    return Channel(field=dim.key, type=kind, label=dim.label, sort=order)


def _y_channel(measure: str) -> Channel:
    m = MEASURES[measure]
    return Channel(field=m.key, type="quantitative", label=m.label, unit=m.unit)


# ---------- builders ----------


def build_chart(
    plan: QueryPlan,
    groups: GroupedStudies,
    *,
    now_year: int,
    citations_per_datum: int = 5,
) -> ChartResult:
    studies = {nct_id(s): s for _, members in groups for s in members}
    if plan.chart_type is ChartType.METRIC or plan.dimension is None:
        return _metric(plan, groups, studies, citations_per_datum)
    dim = DIMENSIONS[plan.dimension]
    if plan.chart_type is ChartType.NETWORK_GRAPH:
        all_studies = [s for _, members in groups for s in members]
        viz, network, linked = build_network(plan, all_studies, studies, citations_per_datum)
        meta = ChartMeta(
            counting_rule="Node size = distinct trials with that entity; edge width = distinct "
            "trials with both.",
            additive=False,
            unique_trials=linked,
            network=network,
        )
        return ChartResult(viz, meta)
    if plan.chart_type is ChartType.SCATTER_PLOT:
        return _scatter(plan, dim, studies, citations_per_datum)
    if dim.kind is DimensionKind.NUMERIC:
        return _histogram(plan, dim, groups, studies, citations_per_datum)
    return _bars(plan, dim, groups, studies, now_year, citations_per_datum)


def _bars(
    plan: QueryPlan,
    dim: Dimension,
    groups: GroupedStudies,
    studies: dict[str, dict[str, Any]],
    now_year: int,
    limit: int,
) -> ChartResult:
    measure = plan.measure
    years = (
        year_range([s for _, m in groups for s in m], dim, plan, now_year)
        if dim.kind is DimensionKind.TIME
        else None
    )
    groupings: list[tuple[str | None, Grouping]] = [
        (label, group(members, dim, plan, years=years)) for label, members in groups
    ]
    measured = {
        (label, key): _measure(bucket, measure, studies)
        for label, g in groupings
        for key, bucket in g.buckets.items()
    }
    labels = {k: b.label for _, g in groupings for k, b in g.buckets.items()}
    totals: dict[str, float] = dict.fromkeys(labels, 0.0)
    for (_, key), m in measured.items():
        totals[key] += m.value
    keys, sort, notes = _sorted_keys(dim, plan, totals, labels)

    comparison = len(groupings) > 1
    rows = []
    for label, g in groupings:
        for key in keys:
            bucket = g.buckets.get(key, Bucket(key, labels[key]))
            m = measured.get((label, key), Measured(0, {}))
            row: dict[str, Any] = {
                "key": f"{label}|{key}" if comparison else key,
                dim.key: labels[key],
                measure: m.value,
            }
            if comparison:
                row["group"] = label
            if dim.kind is DimensionKind.TIME:
                row["estimated_count"] = len(bucket.estimated & set(m.evidence))
            rows.append(row | sample_citations(m.evidence, studies, limit))

    placed = set().union(*(g.placed for _, g in groupings))
    excluded: Counter[str] = Counter()
    for _, g in groupings:
        excluded.update(g.excluded)
    if measure != "trial_count":
        missing = _no_enrollment(placed, studies)
        if missing:
            excluded["no enrollment reported"] += missing

    encoding = {"x": _x_channel(dim, sort), "y": _y_channel(measure)}
    if comparison:
        encoding["color"] = Channel(field="group", type="nominal", label="Group")
    if dim.kind is DimensionKind.TIME:
        chart_type = ChartType.TIME_SERIES
    else:
        chart_type = ChartType.GROUPED_BAR_CHART if comparison else ChartType.BAR_CHART

    overlap = None
    if comparison:
        members = {label: {nct_id(s) for s in ms} for label, ms in groups}
        overlap = [
            {"groups": [a, b], "trials": len(members[a] & members[b])}
            for a, b in combinations(members, 2)
        ]

    viz = Visualization(
        type=chart_type,
        title=_title(plan, dim),
        summary=_summary(rows, dim, measure, len(placed)),
        encoding=encoding,
        data=rows,
    )
    meta = ChartMeta(
        counting_rule=dim.counting_rule,
        additive=not dim.multi_valued and plan.options.phase_mode != "split",
        unique_trials=len(placed),
        excluded=[Excluded(reason=r, count=c) for r, c in excluded.items()],
        sort=sort,
        notes=notes,
        group_overlap=overlap,
    )
    return ChartResult(viz, meta)


def _nice_width(raw: float) -> float:
    if raw <= 0:
        return 1
    magnitude = 10.0 ** math.floor(math.log10(raw))
    return float(next(m * magnitude for m in (1, 2, 5, 10) if m * magnitude >= raw))


def _histogram(
    plan: QueryPlan,
    dim: Dimension,
    groups: GroupedStudies,
    studies: dict[str, dict[str, Any]],
    limit: int,
) -> ChartResult:
    values = {i: extract_number(s, dim.key) for i, s in studies.items()}
    known = {i: n for i, n in values.items() if n is not None}
    excluded = Counter({f"no {dim.label.lower()} reported": len(values) - len(known)})
    if dim.key == "duration_months":
        impossible = [i for i, n in known.items() if n.value < 0]
        for i in impossible:
            del known[i]
        excluded["completion before start (data error)"] += len(impossible)

    ordered = sorted(n.value for n in known.values())
    upper = ordered[math.ceil(0.99 * len(ordered)) - 1] if ordered else 0  # nearest-rank P99
    width = _nice_width(upper / (plan.options.histogram_bins or DEFAULT_BINS))
    bins = int(upper // width) + 1
    members: list[dict[str, tuple[Evidence, ...]]] = [{} for _ in range(bins + 1)]
    for i, n in known.items():
        index = min(int(n.value // width), bins) if n.value <= upper else bins
        members[index][i] = n.evidence

    rows = []
    for index, trials in enumerate(members):
        overflow = index == bins
        if overflow and not trials:
            continue
        start = index * width
        rows.append(
            {
                "key": f"{start:g}+" if overflow else f"{start:g}-{start + width:g}",
                "bin_start": int(start) if float(start).is_integer() else start,
                "bin_end": None if overflow else int(start + width),
                "count": len(trials),
                "is_overflow": overflow,
            }
            | sample_citations(trials, studies, limit)
        )

    viz = Visualization(
        type=ChartType.HISTOGRAM,
        title=f"Distribution of {dim.label.lower()}",
        summary=f"{len(known)} trials have a reported {dim.label.lower()}.",
        encoding={
            "x": Channel(field="bin_start", type="quantitative", label=dim.label),
            "y": Channel(
                field="count", type="quantitative", label="Number of trials", unit="trials"
            ),
        },
        data=rows,
    )
    meta = ChartMeta(
        counting_rule=dim.counting_rule,
        additive=True,
        unique_trials=len(known),
        excluded=[Excluded(reason=r, count=c) for r, c in excluded.items() if c],
        sort=Sort(by="x", order="asc"),
        notes=[f"Bins are {width:g} wide; values above {upper:g} (99th percentile) overflow."],
    )
    return ChartResult(viz, meta)


def _scatter(
    plan: QueryPlan, x_dim: Dimension, studies: dict[str, dict[str, Any]], limit: int
) -> ChartResult:
    assert plan.dimension_2 is not None
    y_dim = DIMENSIONS[plan.dimension_2]
    rows, missing = [], 0
    for trial in sorted(studies):
        x, y = extract_number(studies[trial], x_dim.key), extract_number(studies[trial], y_dim.key)
        if x is None or y is None or (y_dim.key == "duration_months" and y.value < 0):
            missing += 1
            continue
        rows.append(
            {
                "key": trial,
                "nct_id": trial,
                x_dim.key: x.value,
                y_dim.key: y.value,
                "estimated": x.estimated or y.estimated,
            }
            | sample_citations({trial: x.evidence + y.evidence}, studies, limit)
        )
    viz = Visualization(
        type=ChartType.SCATTER_PLOT,
        title=f"{x_dim.label} vs {y_dim.label.lower()}",
        summary=f"{len(rows)} trials have both values.",
        encoding={
            "x": Channel(field=x_dim.key, type="quantitative", label=x_dim.label),
            "y": Channel(field=y_dim.key, type="quantitative", label=y_dim.label),
            "id": Channel(field="nct_id", type="nominal", label="Trial"),
        },
        data=rows,
    )
    excluded = [Excluded(reason=f"no {x_dim.key} or {y_dim.key} reported", count=missing)]
    return ChartResult(
        viz,
        ChartMeta(
            counting_rule="One point per trial with both values.",
            additive=True,
            unique_trials=len(rows),
            excluded=excluded if missing else [],
        ),
    )


def _metric(
    plan: QueryPlan,
    groups: GroupedStudies,
    studies: dict[str, dict[str, Any]],
    limit: int,
) -> ChartResult:
    every = Bucket("all", "Matching trials")
    for i, study in studies.items():
        every.trials[i] = (Evidence("protocolSection.identificationModule.nctId", nct_id(study)),)
    m = _measure(every, plan.measure, studies)
    measure = MEASURES[plan.measure]
    row = {"key": "all", "value": m.value, "label": measure.label} | sample_citations(
        m.evidence, studies, limit
    )
    excluded = []
    if plan.measure != "trial_count":
        missing = _no_enrollment(set(studies), studies)
        if missing:
            excluded.append(Excluded(reason="no enrollment reported", count=missing))
    viz = Visualization(
        type=ChartType.METRIC,
        title=measure.label + " in matching trials"
        if plan.measure != "trial_count"
        else "Matching trials",
        summary=f"{m.value:g} {measure.unit}.",
        encoding={
            "value": Channel(
                field="value", type="quantitative", label=measure.label, unit=measure.unit
            )
        },
        data=[row],
    )
    return ChartResult(
        viz,
        ChartMeta(
            counting_rule="Each matching trial is counted once.",
            additive=True,
            unique_trials=len(studies),
            excluded=excluded,
        ),
    )


# ---------- templates (narrator fallback) ----------


def _title(plan: QueryPlan, dim: Dimension) -> str:
    measure = MEASURES[plan.measure].label
    if dim.kind is DimensionKind.TIME:
        title = f"{measure} per {dim.label.lower()}"
    else:
        title = f"{measure} by {dim.label.lower()}"
    if plan.groups:
        title += ": " + " vs ".join(g.label for g in plan.groups)
    return title


def _summary(rows: list[dict[str, Any]], dim: Dimension, measure: str, trials: int) -> str:
    top = max(rows, key=lambda r: r[measure], default=None)
    if top is None or not top[measure]:
        return f"{trials} trials matched."
    where = f" ({top['group']})" if "group" in top else ""
    return (
        f"{trials} trials matched; {top[dim.key]}{where} has the highest value ({top[measure]:g})."
    )
