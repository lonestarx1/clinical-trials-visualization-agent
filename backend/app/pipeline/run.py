"""Run a validated QueryPlan through the deterministic pipeline (design Q2, stages 4-8 and 11)."""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from app.agents.narrator import Narration
from app.ctgov.client import CtgovClient
from app.ctgov.compiler import compile_plan
from app.ctgov.retrieval import fields_for
from app.pipeline.charts import ChartMeta, build_chart
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

Narrator = Callable[[QueryPlan, Visualization, ChartMeta], Awaitable[Narration]]

YEAR_FILTER_NOTE = "The year filter excludes trials without a start date."


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def _mostly_estimated(viz: Visualization, plan: QueryPlan) -> list[str]:
    """Design Q10, D10.8: flag time buckets where most trials have estimated dates."""
    if "estimated_count" not in (viz.data[0] if viz.data else {}):
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


async def run_plan(
    plan: QueryPlan,
    ctgov: CtgovClient,
    *,
    base_url: str,
    citations_per_datum: int = 5,
    now: datetime | None = None,
    narrator: Narrator | None = None,
) -> QueryResponse:
    started = time.perf_counter()
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
    if not any(counts):
        meta.details = {"search_counts": [{"group": s.group, "count": 0} for s in searches]}
        meta.timings_ms = {"total": _ms(started)}
        return QueryResponse(status="no_matching_trials", visualization=None, meta=meta)

    retrieve_start = time.perf_counter()
    fields = fields_for(plan)
    results = await asyncio.gather(*(ctgov.fetch_all(s, fields) for s in searches))
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
    meta.timings_ms["total"] = _ms(started)
    return QueryResponse(status="ok", visualization=chart.visualization, meta=meta)
