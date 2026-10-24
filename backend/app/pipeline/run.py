"""Run a validated QueryPlan through the deterministic pipeline (design Q2, stages 4-8 and 11).

prepare(): compile + count every search (cheap) and estimate the fetch time.
execute(): fetch, aggregate, build the chart, verify citations, narrate.
"""

import asyncio
import logging
import math
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.agents.narrator import Narration
from app.ctgov.client import PAGE_SIZE, CtgovClient, InconsistentResults, VersionInfo
from app.ctgov.compiler import Search, compile_plan
from app.ctgov.essie import Area, Range
from app.ctgov.retrieval import DATE_TYPE_PIECE, count_per_year, fields_for
from app.pipeline.charts import ChartMeta, ChartResult, build_chart, counted_time_series
from app.pipeline.citations import verify_citations
from app.registry import DIMENSIONS, ChartType, DimensionKind
from app.schemas.plan import QueryPlan
from app.schemas.response import (
    ApiQuery,
    CitationsMeta,
    Interpretation,
    Meta,
    QueryResponse,
    Visualization,
)

YEAR_FILTER_NOTE = "The year filter excludes trials without a start date."
SECONDS_PER_PAGE = 1.6  # measured: ~1.1-2.2 s per 1,000-trial page, within 40 requests/min
SECONDS_PER_CALL = 1.5  # one request start per 1.5 s at 40 requests/min
MAX_COUNTED_YEARS = 60
COUNTED_NOTE = (
    "Counted with one ClinicalTrials.gov count per year instead of downloading every trial; "
    "each year cites its most recent trials."
)

log = logging.getLogger(__name__)

Narrator = Callable[[QueryPlan, Visualization, ChartMeta], Awaitable[Narration]]
Progress = Callable[[int, int], Awaitable[None]]  # (pages_done, pages_total)


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def _mostly_estimated(viz: Visualization, plan: QueryPlan) -> list[str]:
    """Design Q10, D10.8: flag time buckets where most trials have estimated dates."""
    if not isinstance(viz.data, list) or "estimated_count" not in (viz.data[0] if viz.data else {}):
        return []
    years = [
        str(r[plan.dimension or ""])
        for r in viz.data
        if r[plan.measure] and r["estimated_count"] * 2 > r["citation_count"]
    ]
    if not years:
        return []
    return [f"Most trials in {', '.join(dict.fromkeys(years))} have estimated (planned) dates."]


def _filters_meta(plan: QueryPlan) -> dict[str, Any]:
    filters: dict[str, Any] = plan.filters.model_dump(mode="json", exclude_defaults=True)
    if plan.groups:
        filters["groups"] = [
            {"label": g.label, **g.filters.model_dump(mode="json", exclude_defaults=True)}
            for g in plan.groups
        ]
    return filters


def yearly_span(plan: QueryPlan, *, now_year: int) -> tuple[int, int] | None:
    """Years to count one by one (S2), when the plan is a plain trials-per-year series."""
    if plan.measure != "trial_count" or not plan.dimension or plan.dimension_2 or plan.groups:
        return None
    dim = DIMENSIONS[plan.dimension]
    if dim.kind is not DimensionKind.TIME or plan.chart_type is not ChartType.TIME_SERIES:
        return None
    lo, hi = plan.filters.start_year_min, plan.filters.start_year_max or now_year
    if lo is None or hi - lo + 1 > MAX_COUNTED_YEARS:
        return None
    return lo, hi


@dataclass
class Prepared:
    plan: QueryPlan
    searches: list[Search]
    counts: list[int]
    version: VersionInfo
    meta: Meta
    span: tuple[int, int] | None = None  # set when years are counted, not downloaded
    started: float = field(default_factory=time.perf_counter)

    @property
    def pages(self) -> int:
        return sum(math.ceil(n / PAGE_SIZE) for n in self.counts if n)

    @property
    def counted_calls(self) -> int:
        if self.span is None or self.plan.dimension is None:
            return 0
        years = self.span[1] - self.span[0] + 1
        per_year = 3 if self.plan.dimension in DATE_TYPE_PIECE else 2  # count, estimated, sample
        return 1 + years * per_year

    @property
    def estimated_seconds(self) -> int:
        if self.span is not None:
            return math.ceil(self.counted_calls * SECONDS_PER_CALL)
        return math.ceil(self.pages * SECONDS_PER_PAGE)

    @property
    def empty(self) -> bool:
        return not any(self.counts)


@dataclass
class Executed:
    response: QueryResponse
    chart: ChartResult | None
    searches: list[dict[str, Any]]  # params + total count, for revalidation


async def prepare(
    plan: QueryPlan, ctgov: CtgovClient, *, citations_per_datum: int, now: datetime | None = None
) -> Prepared:
    now = now or datetime.now(UTC)
    searches = compile_plan(plan)
    meta = Meta(
        interpretation=Interpretation(
            intent=plan.intent,
            chart_type=plan.chart_type,
            dimension=plan.dimension,
            dimension_2=plan.dimension_2,
            measure=plan.measure,
        ),
        filters=_filters_meta(plan),
        assumptions=list(plan.assumptions),
        warnings=[w for s in searches for w in s.warnings],
        citations=CitationsMeta(per_datum=citations_per_datum),
        trace_id=str(uuid.uuid4()),
        retrieved_at=now.isoformat(timespec="seconds"),
    )
    if plan.filters.start_year_min or plan.filters.start_year_max:
        meta.notes.append(YEAR_FILTER_NOTE)
    version, counts = await asyncio.gather(
        ctgov.version(), asyncio.gather(*(ctgov.count(s) for s in searches))
    )
    meta.data_timestamp = version.data_timestamp
    span = yearly_span(plan, now_year=now.year)
    return Prepared(plan, searches, list(counts), version, meta, span)


async def _counted_years(
    prepared: Prepared, ctgov: CtgovClient, base_url: str, limit: int
) -> tuple[ChartResult, dict[str, dict[str, Any]]]:
    """Trials per year from count calls plus one small sample page per year."""
    plan, search, span = prepared.plan, prepared.searches[0], prepared.span
    assert plan.dimension is not None and span is not None
    dim = DIMENSIONS[plan.dimension]
    assert dim.filter_piece is not None
    counts = await count_per_year(ctgov, search, dim, span)
    year_searches = {
        y: search.narrow(Area(dim.filter_piece, Range(f"{y}-01-01", f"{y}-12-31")))
        for y in counts.years
    }
    wanted = [y for y, n in counts.years.items() if n]
    pages = await asyncio.gather(
        *(
            ctgov.first_page(
                year_searches[y], fields_for(plan), limit, sort=f"{dim.filter_piece}:desc"
            )
            for y in wanted
        )
    )
    samples = dict(zip(wanted, pages, strict=True))
    urls = {y: s.url(base_url) for y, s in year_searches.items()}
    chart = counted_time_series(plan, counts, samples, limit, search_urls=urls)
    studies = {
        s["protocolSection"]["identificationModule"]["nctId"]: s for page in pages for s in page
    }
    return chart, studies


async def execute(
    prepared: Prepared,
    ctgov: CtgovClient,
    *,
    base_url: str,
    citations_per_datum: int = 5,
    now: datetime | None = None,
    narrator: Narrator | None = None,
    progress: Progress | None = None,
) -> Executed:
    searches, meta = prepared.searches, prepared.meta
    now = now or datetime.now(UTC)
    stored = [
        {"params": s.params, "group": s.group, "total_count": n}
        for s, n in zip(searches, prepared.counts, strict=True)
    ]
    if prepared.empty:
        meta.details = {"search_counts": [{"group": s.group, "count": 0} for s in searches]}
        meta.timings_ms = {"total": _ms(prepared.started)}
        return Executed(
            QueryResponse(status="no_matching_trials", visualization=None, meta=meta), None, stored
        )

    retrieve_start = time.perf_counter()
    counted = None
    if prepared.span is not None:
        try:
            counted = await _counted_years(prepared, ctgov, base_url, citations_per_datum)
        except InconsistentResults as exc:
            log.warning("per-year counts disagree, downloading instead: %s", exc)
    if counted is not None:
        chart, studies = counted
        meta.api_queries = [
            ApiQuery(group=None, url=searches[0].url(base_url), total_count=prepared.counts[0])
        ]
        if meta.citations is not None:
            meta.citations.applied = "sample"
            meta.citations.reason = "counted per year"
        meta.notes.append(COUNTED_NOTE)
        retrieve_ms = _ms(retrieve_start)
        aggregate_start = time.perf_counter()
    else:
        chart, studies, retrieve_ms, aggregate_start = await _downloaded(
            prepared, ctgov, base_url, citations_per_datum, now, progress
        )
    await asyncio.to_thread(verify_citations, chart.visualization, studies)
    return await _finish_chart(prepared, chart, retrieve_ms, aggregate_start, stored, narrator)


async def _downloaded(
    prepared: Prepared,
    ctgov: CtgovClient,
    base_url: str,
    citations_per_datum: int,
    now: datetime,
    progress: Progress | None,
) -> tuple[ChartResult, dict[str, dict[str, Any]], int, float]:
    """Strategy S1: download every matching trial, then aggregate."""
    plan, searches, meta = prepared.plan, prepared.searches, prepared.meta
    retrieve_start = time.perf_counter()
    fields = fields_for(plan)
    done = [0] * len(searches)

    def tracker(index: int) -> Callable[[int], Awaitable[None]] | None:
        if progress is None:
            return None

        async def on_page(pages: int) -> None:
            done[index] = pages
            await progress(sum(done), prepared.pages)

        return on_page

    results = await asyncio.gather(
        *(ctgov.fetch_all(s, fields, tracker(i)) for i, s in enumerate(searches))
    )
    meta.api_queries = [
        ApiQuery(group=s.group, url=s.url(base_url), total_count=r.total_count)
        for s, r in zip(searches, results, strict=True)
    ]
    retrieve_ms = _ms(retrieve_start)

    aggregate_start = time.perf_counter()

    def aggregate() -> tuple[ChartResult, dict[str, dict[str, Any]]]:
        chart = build_chart(
            plan,
            [(s.group, r.studies) for s, r in zip(searches, results, strict=True)],
            now_year=now.year,
            citations_per_datum=citations_per_datum,
        )
        studies = {
            s["protocolSection"]["identificationModule"]["nctId"]: s
            for r in results
            for s in r.studies
        }
        return chart, studies

    # CPU-bound (seconds for large questions): run it off the event loop so other requests
    # keep being served. Threads share the GIL, but the loop still gets its turn every few ms.
    chart, studies = await asyncio.to_thread(aggregate)
    return chart, studies, retrieve_ms, aggregate_start


async def _finish_chart(
    prepared: Prepared,
    chart: ChartResult,
    retrieve_ms: int,
    aggregate_start: float,
    stored: list[dict[str, Any]],
    narrator: Narrator | None,
) -> Executed:
    plan, meta = prepared.plan, prepared.meta
    meta.counting_rule = chart.meta.counting_rule
    meta.additive = chart.meta.additive
    meta.unique_trials = chart.meta.unique_trials
    meta.excluded = chart.meta.excluded
    meta.sort = chart.meta.sort
    meta.notes += chart.meta.notes
    meta.group_overlap = chart.meta.group_overlap
    meta.network = chart.meta.network
    meta.warnings += _mostly_estimated(chart.visualization, plan)
    meta.timings_ms = {"retrieve": retrieve_ms, "aggregate": _ms(aggregate_start)}

    if narrator is not None:
        narrate_start = time.perf_counter()
        narration = await narrator(plan, chart.visualization, chart.meta)
        chart.visualization.title, chart.visualization.summary = narration.title, narration.summary
        meta.narration = {
            "model": narration.model,
            "attempts": narration.attempts,
            "fallback": narration.fallback,
            "errors": narration.errors,
        }
        meta.timings_ms["narrate"] = _ms(narrate_start)
    meta.timings_ms["total"] = _ms(prepared.started)
    response = QueryResponse(status="ok", visualization=chart.visualization, meta=meta)
    return Executed(response, chart, stored)


async def run_plan(
    plan: QueryPlan,
    ctgov: CtgovClient,
    *,
    base_url: str,
    citations_per_datum: int = 5,
    now: datetime | None = None,
    narrator: Narrator | None = None,
) -> QueryResponse:
    """prepare + execute in one go (debug endpoint and tests)."""
    prepared = await prepare(plan, ctgov, citations_per_datum=citations_per_datum, now=now)
    executed = await execute(
        prepared,
        ctgov,
        base_url=base_url,
        citations_per_datum=citations_per_datum,
        now=now,
        narrator=narrator,
    )
    return executed.response
