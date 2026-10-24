"""Run a validated QueryPlan through the deterministic pipeline (design Q2, stages 4-8 and 11).

prepare(): compile + count every search (cheap) and estimate the fetch time.
execute(): fetch, aggregate, build the chart, verify citations, narrate.
"""

import asyncio
import math
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.agents.narrator import Narration
from app.ctgov.client import PAGE_SIZE, CtgovClient, VersionInfo
from app.ctgov.compiler import Search, compile_plan
from app.ctgov.retrieval import fields_for
from app.pipeline.charts import ChartMeta, ChartResult, build_chart
from app.pipeline.citations import verify_citations
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


@dataclass
class Prepared:
    plan: QueryPlan
    searches: list[Search]
    counts: list[int]
    version: VersionInfo
    meta: Meta
    started: float = field(default_factory=time.perf_counter)

    @property
    def pages(self) -> int:
        return sum(math.ceil(n / PAGE_SIZE) for n in self.counts if n)

    @property
    def estimated_seconds(self) -> int:
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
    return Prepared(plan, searches, list(counts), version, meta)


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
    plan, searches, meta = prepared.plan, prepared.searches, prepared.meta
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
    chart = build_chart(
        plan,
        [(s.group, r.studies) for s, r in zip(searches, results, strict=True)],
        now_year=now.year,
        citations_per_datum=citations_per_datum,
    )
    studies = {
        s["protocolSection"]["identificationModule"]["nctId"]: s for r in results for s in r.studies
    }
    verify_citations(chart.visualization, studies)

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
