"""Grouped trials -> visualization spec + chart metadata (design Q3, Q9, Q10, Q12, Q14).

Titles here are templates. The narrator (M2) replaces them, and falls back to
these when its output fails the checks (Q4b). There is no summary (Q4b revision).
"""

import math
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Literal

from app.ctgov.retrieval import YearCounts
from app.pipeline.aggregate import NOT_REPORTED, Bucket, Grouping, group, nct_id, year_range
from app.pipeline.citations import citation, ordered_trials, sample_citations
from app.pipeline.extract import Evidence, extract, extract_number
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
    # Every contributing trial's citation per data point (by row key), for stored results.
    full_citations: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # Data points whose answer read only a sample: the API search that lists all their trials,
    # paged by the citations endpoint when asked (design Q14).
    citation_sources: dict[str, dict[str, Any]] = field(default_factory=dict)


# ---------- measures ----------


@dataclass
class Measured:
    value: float
    evidence: dict[str, tuple[Evidence, ...]]  # contributing trials -> evidence


ENROLLMENT_MEASURES = {"total_enrollment", "median_enrollment"}


def measure_text(plan: QueryPlan) -> tuple[str, str]:
    """(label, unit) of the plan's measure; distinct_count names its entity and threshold."""
    entity = plan.options.count_entity
    if plan.measure != "distinct_count" or entity is None:
        m = MEASURES[plan.measure]
        return m.label, m.unit
    plural = _plural(DIMENSIONS[entity]).lower()
    least = plan.options.min_trials or 1
    if least == 1:
        return f"Number of {plural}", plural
    return f"{plural[:1].upper()}{plural[1:]} with at least {least} trials", plural


def _distinct(bucket: Bucket, plan: QueryPlan, studies: dict[str, dict[str, Any]]) -> Measured:
    """Entities with at least min_trials of the bucket's trials; evidence = those trials."""
    entity, least = plan.options.count_entity or "", plan.options.min_trials or 1
    trials_of: dict[str, dict[str, tuple[Evidence, ...]]] = {}
    for i, evidence in bucket.trials.items():
        for value in extract(
            studies[i], entity, condition_source=plan.options.condition_source or "mesh"
        ):
            trials_of.setdefault(value.key, {})[i] = evidence + value.evidence
    kept = [trials for trials in trials_of.values() if len(trials) >= least]
    evidence_by_trial: dict[str, tuple[Evidence, ...]] = {}
    for trials in kept:
        for i, evidence in trials.items():
            evidence_by_trial[i] = evidence_by_trial.get(i, ()) + tuple(
                e for e in evidence if e not in evidence_by_trial.get(i, ())
            )
    return Measured(len(kept), evidence_by_trial)


def _measure(bucket: Bucket, plan: QueryPlan, studies: dict[str, dict[str, Any]]) -> Measured:
    measure = plan.measure
    if measure == "trial_count":
        return Measured(len(bucket.trials), dict(bucket.trials))
    if measure == "distinct_count":
        return _distinct(bucket, plan, studies)
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


def _y_channel(plan: QueryPlan) -> Channel:
    label, unit = measure_text(plan)
    return Channel(field=plan.measure, type="quantitative", label=label, unit=unit)


# ---------- builders ----------


def build_chart(
    plan: QueryPlan,
    groups: GroupedStudies,
    *,
    now_year: int,
    citations_per_datum: int = 5,
) -> ChartResult:
    result = _build(plan, groups, now_year=now_year, citations_per_datum=citations_per_datum)
    data = result.visualization.data
    points = [*data["nodes"], *data["edges"]] if isinstance(data, dict) else data
    for point in points:
        result.full_citations[str(point["key"])] = point.pop("_full", [])
    return result


def _build(
    plan: QueryPlan,
    groups: GroupedStudies,
    *,
    now_year: int,
    citations_per_datum: int,
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
    if plan.dimension_2 and not plan.groups:
        series_dim = DIMENSIONS[plan.dimension_2]
        split = _split_series(plan, series_dim, [s for _, m in groups for s in m])
        return _bars(plan, dim, split, studies, now_year, citations_per_datum, series=series_dim)
    return _bars(plan, dim, groups, studies, now_year, citations_per_datum)


MAX_SERIES = 6


def _split_series(
    plan: QueryPlan, series: Dimension, studies: Sequence[dict[str, Any]]
) -> list[tuple[str | None, list[dict[str, Any]]]]:
    """One group of trials per value of the series dimension (a trial can be in several)."""
    buckets = group(studies, series, plan.model_copy(update={"filters": plan.filters}))
    labels = {k: b.label for k, b in buckets.buckets.items()}
    sizes = {k: float(len(b.trials)) for k, b in buckets.buckets.items()}
    keys, _, _ = _sorted_keys(
        series,
        plan.model_copy(
            update={
                "options": plan.options.model_copy(
                    update={"top_n": MAX_SERIES if series.kind is DimensionKind.ENTITY else None}
                )
            }
        ),
        sizes,
        labels,
    )
    by_id = {nct_id(s): s for s in studies}
    return [(labels[k], [by_id[i] for i in buckets.buckets[k].trials]) for k in keys]


def _bars(
    plan: QueryPlan,
    dim: Dimension,
    groups: GroupedStudies,
    studies: dict[str, dict[str, Any]],
    now_year: int,
    limit: int,
    series: Dimension | None = None,
) -> ChartResult:
    """Bars or a time series; several groups (comparison) or series (split by `series`)."""
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
        (label, key): _measure(bucket, plan, studies)
        for label, g in groupings
        for key, bucket in g.buckets.items()
    }
    labels = {k: b.label for _, g in groupings for k, b in g.buckets.items()}
    totals: dict[str, float] = dict.fromkeys(labels, 0.0)
    for (_, key), m in measured.items():
        totals[key] += m.value
    keys, sort, notes = _sorted_keys(dim, plan, totals, labels)

    comparison = len(groupings) > 1 or series is not None
    color_field = series.key if series else "group"
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
                row[color_field] = label
            if dim.kind is DimensionKind.TIME:
                row["estimated_count"] = len(bucket.estimated & set(m.evidence))
            rows.append(row | sample_citations(m.evidence, studies, limit))

    placed = set().union(*(g.placed for _, g in groupings))
    excluded: Counter[str] = Counter()
    for _, g in groupings:
        excluded.update(g.excluded)
    if measure in ENROLLMENT_MEASURES:
        missing = _no_enrollment(placed, studies)
        if missing:
            excluded["no enrollment reported"] += missing

    encoding = {"x": _x_channel(dim, sort), "y": _y_channel(plan)}
    if comparison:
        encoding["color"] = Channel(
            field=color_field, type="nominal", label=series.label if series else "Group"
        )
    if dim.kind is DimensionKind.TIME:
        chart_type = ChartType.TIME_SERIES
    else:
        chart_type = ChartType.GROUPED_BAR_CHART if comparison else ChartType.BAR_CHART

    overlap = None
    if comparison and series is None:
        members = {label: {nct_id(s) for s in ms} for label, ms in groups}
        overlap = [
            {"groups": [a, b], "trials": len(members[a] & members[b])}
            for a, b in combinations(members, 2)
        ]

    viz = Visualization(
        type=chart_type,
        title=_title(plan, dim),
        encoding=encoding,
        data=rows,
    )
    meta = ChartMeta(
        counting_rule=_distinct_rule(plan, f"each {dim.label.lower()}") or dim.counting_rule,
        additive=not dim.multi_valued
        and plan.options.phase_mode != "split"
        and plan.measure != "distinct_count",
        unique_trials=len(placed),
        excluded=[Excluded(reason=r, count=c) for r, c in excluded.items()],
        sort=sort,
        notes=notes,
        group_overlap=overlap,
    )
    return ChartResult(viz, meta)


def counted_time_series(
    plan: QueryPlan,
    counts: YearCounts,
    samples: dict[int, list[dict[str, Any]]],
    limit: int,
    search_urls: dict[int, str] | None = None,
) -> ChartResult:
    """Trials per year from count calls; each year cites a sample of its most recent trials.

    `search_urls` (year -> API search) lets a reader open every trial of a year.
    """
    assert plan.dimension is not None
    dim = DIMENSIONS[plan.dimension]
    totals = {str(y): float(n) for y, n in counts.years.items()}
    keys, sort, notes = _sorted_keys(dim, plan, totals, {k: k for k in totals})
    result_citations: dict[str, list[dict[str, Any]]] = {}
    rows = []
    for key in keys:
        year, n = int(key), counts.years[int(key)]
        by_id = {nct_id(s): s for s in samples.get(year, [])}
        evidence = {
            i: values[0].evidence
            for i, s in by_id.items()
            if (values := extract(s, dim.key)) and values[0].key == key
        }
        cited = [citation(by_id[i], evidence[i]) for i in ordered_trials(evidence, by_id)][:limit]
        result_citations[key] = cited
        rows.append(
            {
                "key": key,
                dim.key: key,
                "trial_count": n,
                "estimated_count": counts.estimated[year],
                "citation_count": n,
                "citations": cited,
                "citations_truncated": n > len(cited),
            }
            | ({"search_url": search_urls[year]} if search_urls else {})
        )
    viz = Visualization(
        type=ChartType.TIME_SERIES,
        title=_title(plan, dim),
        encoding={"x": _x_channel(dim, sort), "y": _y_channel(plan)},
        data=rows,
    )
    meta = ChartMeta(
        counting_rule=dim.counting_rule,
        additive=True,
        unique_trials=counts.within,
        sort=sort,
        notes=notes,
    )
    return ChartResult(viz, meta, result_citations)


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
    m = _measure(every, plan, studies)
    label, unit = measure_text(plan)
    row = {"key": "all", "value": m.value, "label": label} | sample_citations(
        m.evidence, studies, limit
    )
    excluded = []
    if plan.measure in ENROLLMENT_MEASURES:
        missing = _no_enrollment(set(studies), studies)
        if missing:
            excluded.append(Excluded(reason="no enrollment reported", count=missing))
    viz = Visualization(
        type=ChartType.METRIC,
        title=label + " in matching trials" if plan.measure != "trial_count" else "Matching trials",
        encoding={"value": Channel(field="value", type="quantitative", label=label, unit=unit)},
        data=[row],
    )
    return ChartResult(
        viz,
        ChartMeta(
            counting_rule=_distinct_rule(plan, "the matching trials")
            or "Each matching trial is counted once.",
            additive=plan.measure != "distinct_count",
            unique_trials=len(studies),
            excluded=excluded,
        ),
    )


# ---------- templates (narrator fallback) ----------


def _distinct_rule(plan: QueryPlan, where: str) -> str | None:
    if plan.measure != "distinct_count" or plan.options.count_entity is None:
        return None
    _, plural = measure_text(plan)
    least = plan.options.min_trials or 1
    return (
        f"Each value is the number of distinct {plural} with at least {least} matching "
        f"trial{'s' if least > 1 else ''} in {where}; their trials are the citations."
    )


def _title(plan: QueryPlan, dim: Dimension) -> str:
    measure = measure_text(plan)[0]
    if dim.kind is DimensionKind.TIME:
        title = f"{measure} per {dim.label.lower()}"
    else:
        title = f"{measure} by {dim.label.lower()}"
    if plan.groups:
        title += ": " + " vs ".join(g.label for g in plan.groups)
    return title
