"""Answer a question (design Q2, Q6, Q8): guard ∥ planner -> gate -> pipeline -> narrator.

With a database: the plan cache (L2) skips the planner for a repeated request,
the result cache (L3) reuses a stored answer after revalidation, broad
questions become background jobs, LLM usage is recorded and capped per day.
"""

import asyncio
import logging
import random
import time
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.guard import check_request
from app.agents.narrator import narrate
from app.agents.planner import PlannerResult, plan_request
from app.core.config import Settings
from app.ctgov.client import CtgovClient, FetchResult
from app.ctgov.compiler import Search
from app.ctgov.essie import Area, Range
from app.llm.client import LLM, UsageLog
from app.mirror.fast import FastUnavailable, differences, fetch_from_mirror
from app.pipeline.keys import planner_version, request_key, result_key
from app.pipeline.run import Executed, Prepared, elapsed_ms, execute, prepare, run_plan
from app.schemas.plan import QueryPlan
from app.schemas.request import QueryRequest
from app.schemas.response import Meta, QueryResponse
from app.store import jobs, plans, results, usage

log = logging.getLogger(__name__)
Sessions = async_sessionmaker[AsyncSession]


class RejectedByPolicy(Exception):
    """The guard classified the request as malicious (400). The reason is logged only."""


class BudgetExceeded(Exception):
    """Today's LLM spending cap is reached (503 budget_exceeded)."""


class TooManyJobs(Exception):
    """This client already has the maximum number of active background jobs (429)."""


class JobCancelled(Exception):
    """The job's row says `cancelled` (DELETE /v1/jobs/{id}): stop, and write nothing more."""


CANCEL_CHECK_SECONDS = 1.0  # how often a running job checks its row, besides each page


async def stop_when_cancelled[T](
    work: Coroutine[Any, Any, T], cancelled: Callable[[], Awaitable[bool]], *, every: float
) -> T:
    """Run `work`, checking `cancelled()` every `every` seconds; cancel it and raise
    JobCancelled once it says so.

    This covers the stages that report no page progress (per-year counts, aggregation,
    narration). A failed check (e.g. the database briefly down) is not a cancel.
    """
    task = asyncio.ensure_future(work)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=every)
            if done:
                return task.result()
            try:
                stop = await cancelled()
            except Exception:
                log.warning("could not check whether the job was cancelled", exc_info=True)
                continue
            if stop:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise JobCancelled
    finally:
        task.cancel()  # a no-op once done; stops the work if the worker itself is stopping


@dataclass
class StageLLMs:
    guard: LLM
    planner: LLM
    narrator: LLM

    def usage(self) -> UsageLog:
        logs = {id(m.usage): m.usage for m in (self.guard, self.planner, self.narrator)}
        return UsageLog([c for usage_log in logs.values() for c in usage_log.calls])


LLMFactory = Callable[[UsageLog], StageLLMs]


@dataclass
class JobAccepted:
    job_id: uuid.UUID
    estimated_seconds: int


@dataclass
class Context:
    """What the synchronous part learned; carried into a background job."""

    guard: dict[str, Any]
    planner: dict[str, Any]
    warnings: list[str]
    chart_type_source: str
    cache: dict[str, str]
    trace_id: str
    timings_ms: dict[str, int] = field(default_factory=dict)  # `plan`: guard + planner


def _finish(response: QueryResponse, ctx: Context, llms: StageLLMs) -> QueryResponse:
    meta = response.meta
    meta.guard, meta.planner, meta.cache, meta.trace_id = (
        ctx.guard,
        ctx.planner,
        ctx.cache,
        ctx.trace_id,
    )
    meta.warnings = ctx.warnings + [w for w in meta.warnings if w not in ctx.warnings]
    if meta.interpretation is not None:
        meta.interpretation.chart_type_source = ctx.chart_type_source  # type: ignore[assignment]
    meta.usage = llms.usage().summary()
    return response


def _datums(executed: Executed, plan: QueryPlan) -> list[results.Datum]:
    chart = executed.chart
    if chart is None:
        return []
    data: Any = chart.visualization.data
    points = [*data["nodes"], *data["edges"]] if isinstance(data, dict) else data
    out = []
    for p in points:
        label = (
            p.get("label")
            or p.get(plan.dimension or "")
            or f"{p.get('source', '')} - {p.get('target', '')}"
        )
        value = next((p[k] for k in (plan.measure, "value", "count", "weight") if k in p), None)
        key = str(p["key"])
        source = chart.citation_sources.get(key)
        out.append(
            results.Datum(
                key,
                str(label),
                value,
                chart.full_citations.get(key, []),
                count=source["count"] if source else None,
                source=source,
            )
        )
    return out


async def store_answer(
    sessions: Sessions,
    executed: Executed,
    *,
    plan: QueryPlan,
    request: QueryRequest,
    settings: Settings,
    version: tuple[str, str],
) -> uuid.UUID:
    response = executed.response
    response.result_id = str(uuid.uuid4())
    async with sessions() as s:
        await results.save_result(
            s,
            result_key=result_key(
                plan, request.citations_per_datum, request.citations, request.mode
            ),
            response=response.model_dump(mode="json"),
            request=request.model_dump(mode="json"),
            plan=plan.model_dump(mode="json"),
            datums=_datums(executed, plan),
            searches=executed.searches,
            data_timestamp=version[0],
            api_version=version[1],
            ttl=timedelta(hours=settings.result_ttl_hours),
        )
        await s.commit()
    return uuid.UUID(response.result_id)


async def _reuse(
    sessions: Sessions, key: str, ctgov: CtgovClient, settings: Settings
) -> tuple[dict[str, Any], str] | None:
    """A stored answer for this plan, if still valid ("hit") or revalidated (Q8)."""
    async with sessions() as s:
        row = await results.latest_valid(s, key)
        if row is None or row.verified_data_ts is None:
            return None
        version = await ctgov.version()
        current = datetime.fromisoformat(version.data_timestamp).replace(tzinfo=UTC)
        if row.verified_data_ts == current:
            return row.response, "hit"
        if row.created_at < datetime.now(UTC) - timedelta(days=settings.revalidation_ceiling_days):
            return None
        since = row.verified_data_ts.date().isoformat()
        for search in row.searches:
            base = Search(search["params"])
            changed = await ctgov.count(
                base.narrow(Area("LastUpdatePostDate", Range(since, "MAX")))
            )
            if changed or await ctgov.count(base) != search["total_count"]:
                return None
        await results.restamp(s, row.result_id, version.data_timestamp, version.api_version)
        await s.commit()
        return row.response, "revalidated"


async def _record_usage(
    sessions: Sessions | None,
    llms: StageLLMs,
    trace_id: str,
    job_id: uuid.UUID | None,
    price_version: str,
) -> None:
    if sessions is None:
        return
    async with sessions() as s:
        await usage.record(
            s,
            llms.usage(),
            trace_id=uuid.UUID(trace_id),
            job_id=job_id,
            price_version=price_version,
        )
        await s.commit()


def _context(
    planned: PlannerResult, guard: dict[str, Any], plan_hit: bool, trace_id: str
) -> Context:
    return Context(
        guard=guard,
        planner={"steps": planned.steps, "tool_calls": planned.tool_calls, "model": planned.model},
        warnings=planned.warnings,
        chart_type_source=planned.chart_type_source,
        cache={"plan": "hit" if plan_hit else "miss"},
        trace_id=trace_id,
    )


async def _answer_without_models(
    request: QueryRequest,
    cached: PlannerResult | None,
    ctgov: CtgovClient,
    llms: StageLLMs,
    settings: Settings,
    sessions: Sessions,
) -> QueryResponse:
    """Today's AI budget is spent: answer only what needs no model call, else 503 (Q16).

    That is a stored plan plus a stored result that is still valid or revalidates (Q8).
    The guard is not called either. This is safe: a plan is cached only after the guard
    passed the request, and the plan-cache key covers the question and every field except
    `citations`, `citations_per_datum` and `mode` (choices and a number, which can't carry an
    attack). So an exact repeat of a guarded request is all that can get through here.
    Anything else (a new question, or a result that would have to be narrated again)
    needs a model and is refused.
    """
    if cached is None or cached.plan is None:
        raise BudgetExceeded
    key = result_key(cached.plan, request.citations_per_datum, request.citations, request.mode)
    reused = await _reuse(sessions, key, ctgov, settings)
    if reused is None:
        raise BudgetExceeded
    stored, how = reused
    guard = {"verdict": "ok", "model": None, "cached": True}
    ctx = _context(cached, guard, True, str(uuid.uuid4()))
    ctx.cache["result"] = how
    return _finish(QueryResponse.model_validate(stored), ctx, llms)


async def handle_query(
    request: QueryRequest,
    *,
    ctgov: CtgovClient,
    llms: StageLLMs,
    settings: Settings,
    sessions: Sessions | None = None,
    client_ip: str | None = None,
    price_version: str = "1",
) -> QueryResponse | JobAccepted:
    started = time.perf_counter()
    trace_id = str(uuid.uuid4())
    rkey = request_key(request, settings)
    cached: PlannerResult | None = None
    over_budget = False
    if sessions is not None:
        async with sessions() as s:
            over_budget = await usage.spent_today(s) >= Decimal(str(settings.llm_daily_budget_usd))
            row = await plans.get(s, rkey)
            await s.commit()
        if row is not None:
            cached = PlannerResult(plan=QueryPlan.model_validate(row.plan), **row.planner_trace)
    if over_budget:
        assert sessions is not None
        return await _answer_without_models(request, cached, ctgov, llms, settings, sessions)

    guard_task = asyncio.create_task(check_request(llms.guard, request))
    plan_task = (
        None
        if cached
        else asyncio.create_task(
            plan_request(llms.planner, request, ctgov, max_steps=settings.planner.max_steps)
        )
    )
    try:
        verdict = await guard_task
    except BaseException:
        if plan_task:
            plan_task.cancel()
        raise
    if verdict.verdict == "malicious":
        if plan_task:
            plan_task.cancel()
        log.info("rejected by guard: %s", verdict.reason)
        await _record_usage(sessions, llms, trace_id, None, price_version)
        raise RejectedByPolicy
    planned = cached or await plan_task  # type: ignore[misc]

    ctx = _context(
        planned, {"verdict": verdict.verdict, "model": verdict.model}, cached is not None, trace_id
    )
    ctx.timings_ms["plan"] = elapsed_ms(started)
    if planned.plan is None or planned.plan.scope == "out_of_scope":
        await _record_usage(sessions, llms, trace_id, None, price_version)
        if planned.plan is None:
            meta = Meta(
                details={"errors": planned.errors, "best_attempt": planned.best_attempt},
                timings_ms={**ctx.timings_ms, "total": elapsed_ms(started)},
            )
            return _finish(
                QueryResponse(status="could_not_interpret", visualization=None, meta=meta),
                ctx,
                llms,
            )
        details = {"reason": planned.plan.scope_reason}
        if planned.plan.scope_suggestion:
            details["suggestion"] = planned.plan.scope_suggestion
        meta = Meta(
            assumptions=planned.plan.assumptions,
            details=details,
            timings_ms={**ctx.timings_ms, "total": elapsed_ms(started)},
        )
        return _finish(
            QueryResponse(status="out_of_scope", visualization=None, meta=meta), ctx, llms
        )

    plan = planned.plan
    if sessions is not None and not cached:
        async with sessions() as s:
            trace = {
                "steps": planned.steps,
                "tool_calls": planned.tool_calls,
                "model": planned.model,
                "warnings": planned.warnings,
                "chart_type_source": planned.chart_type_source,
            }
            await plans.put(s, rkey, planner_version(settings), plan.model_dump(mode="json"), trace)
            await s.commit()

    if sessions is not None:
        reused = await _reuse(
            sessions,
            result_key(plan, request.citations_per_datum, request.citations, request.mode),
            ctgov,
            settings,
        )
        if reused is not None:
            stored, how = reused
            ctx.cache["result"] = how
            await _record_usage(sessions, llms, trace_id, None, price_version)
            return _finish(QueryResponse.model_validate(stored), ctx, llms)
        ctx.cache["result"] = "miss"

    prepared = await prepare(
        plan,
        ctgov,
        citations_per_datum=request.citations_per_datum,
        citations=request.citations,
        started=started,
        timings_ms=ctx.timings_ms,
    )
    fetched = None
    if request.mode == "fast" and not prepared.empty:
        fetched = await _fast(prepared, ctgov, settings, sessions)
    if (
        fetched is None
        and sessions is not None
        and not prepared.empty
        and prepared.estimated_seconds > settings.sync_max_seconds
    ):
        async with sessions() as s:
            if (
                client_ip
                and await jobs.active_for_client(s, client_ip) >= settings.max_active_jobs_per_ip
            ):
                raise TooManyJobs
            job = await jobs.create(
                s,
                request_key=rkey,
                request=request.model_dump(mode="json"),
                plan=plan.model_dump(mode="json"),
                context=ctx.__dict__,
                estimated_seconds=prepared.estimated_seconds,
                trace_id=uuid.UUID(trace_id),
                client_ip=client_ip,
            )
            await s.commit()
        await _record_usage(sessions, llms, trace_id, job.job_id, price_version)
        return JobAccepted(job.job_id, job.estimated_seconds)

    executed = await execute(
        prepared,
        ctgov,
        base_url=settings.ctgov_base_url,
        citations_per_datum=request.citations_per_datum,
        citations_full_max=settings.citations_full_max,
        narrator=partial(narrate, llms.narrator),
        fetched=fetched,
    )
    response = _finish(executed.response, ctx, llms)
    if sessions is not None:
        await store_answer(
            sessions,
            executed,
            plan=plan,
            request=request,
            settings=settings,
            version=(prepared.version.data_timestamp, prepared.version.api_version),
        )
        await _record_usage(sessions, llms, trace_id, None, price_version)
    if fetched is not None:
        _shadow(prepared, request, response, ctgov, settings)
    return response


FAST_OFF = "Fast mode is turned off on this server, so this was answered live."
_SHADOWS: set[asyncio.Task[None]] = set()  # running shadow runs, kept from garbage collection


async def _fast(
    prepared: Prepared, ctgov: CtgovClient, settings: Settings, sessions: Sessions | None
) -> list[FetchResult] | None:
    """The trials from the mirror (design Q22), or None (with a note) to answer live."""
    meta = prepared.meta
    if not settings.fast_mode_enabled or sessions is None:
        meta.notes.append(FAST_OFF)
        return None
    try:
        fetched = await fetch_from_mirror(
            prepared,
            ctgov,
            sessions,
            new_term_max_trials=settings.fast_new_term_max_trials,
            max_trials=settings.fast_max_trials,
        )
    except FastUnavailable as exc:
        meta.notes.append(f"Fast mode wasn't used: {exc}. Answered live.")
        return None
    except Exception:  # the mirror must never break a question: answer live
        log.exception("fast mode failed; answering live")
        meta.notes.append("Fast mode wasn't used: our copy couldn't be read. Answered live.")
        return None
    meta.data_source = "fast"
    meta.notes.append(
        f"Fast mode: read from our copy of ClinicalTrials.gov (data of "
        f"{prepared.version.data_timestamp[:10]}), after ClinicalTrials.gov's search picked "
        "the trials and a live count confirmed their number."
    )
    return fetched


def _shadow(
    prepared: Prepared,
    request: QueryRequest,
    fast: QueryResponse,
    ctgov: CtgovClient,
    settings: Settings,
) -> None:
    """For a sample of small fast answers, compute the live answer too and log any difference."""
    if (
        fast.visualization is None
        or prepared.pages > settings.fast_mode_shadow_max_pages
        or random.random() >= settings.fast_mode_shadow_rate
    ):
        return
    task = asyncio.create_task(
        _compare_live(prepared.plan, request, fast, ctgov, settings.ctgov_base_url)
    )
    _SHADOWS.add(task)
    task.add_done_callback(_SHADOWS.discard)


async def _compare_live(
    plan: QueryPlan, request: QueryRequest, fast: QueryResponse, ctgov: CtgovClient, base_url: str
) -> None:
    try:
        live = await run_plan(
            plan, ctgov, base_url=base_url, citations_per_datum=request.citations_per_datum
        )
        assert fast.visualization is not None and live.visualization is not None
        diff = differences(
            fast.visualization.model_dump(mode="json"), live.visualization.model_dump(mode="json")
        )
    except Exception:
        log.exception("fast-mode shadow run failed (trace %s)", fast.meta.trace_id)
        return
    if diff:
        log.warning("fast-mode drift (trace %s): %s", fast.meta.trace_id, "; ".join(diff[:20]))
    else:
        log.info("fast-mode shadow run matched (trace %s)", fast.meta.trace_id)


async def run_job(
    job_id: uuid.UUID,
    *,
    sessions: Sessions,
    ctgov: CtgovClient,
    llms: StageLLMs,
    settings: Settings,
    price_version: str = "1",
) -> uuid.UUID:
    """Run a claimed job: retrieval, chart, narration; store the answer. Returns the result_id."""
    async with sessions() as s:
        job = await jobs.get(s, job_id)
        assert job is not None
        request = QueryRequest.model_validate(job.request)
        plan = QueryPlan.model_validate(job.plan)
        ctx = Context(**job.context)

    async def cancelled() -> bool:
        async with sessions() as s:
            return await jobs.status(s, job_id) == "cancelled"

    async def progress(done: int, total: int) -> None:
        """After each page: record progress, and stop here if the job was cancelled."""
        async with sessions() as s:
            active = await jobs.progress(
                s, job_id, {"stage": "retrieve", "pages_done": done, "pages_total": total}
            )
            await s.commit()
        if not active:
            raise JobCancelled

    async def work() -> tuple[Prepared, Executed]:
        # `total` = the request's planning time + this run; the wait in the queue is left out.
        prepared = await prepare(
            plan,
            ctgov,
            citations_per_datum=request.citations_per_datum,
            citations=request.citations,
            started=time.perf_counter() - ctx.timings_ms.get("plan", 0) / 1000,
            timings_ms=ctx.timings_ms,
        )
        executed = await execute(
            prepared,
            ctgov,
            base_url=settings.ctgov_base_url,
            citations_per_datum=request.citations_per_datum,
            citations_full_max=settings.citations_full_max,
            narrator=partial(narrate, llms.narrator),
            progress=progress,
        )
        return prepared, executed

    if await cancelled():  # cancelled between the claim and now
        raise JobCancelled
    try:
        prepared, executed = await stop_when_cancelled(
            work(), cancelled, every=CANCEL_CHECK_SECONDS
        )
    except JobCancelled:
        # A narrator call made before the stop was still paid for.
        await _record_usage(sessions, llms, ctx.trace_id, job_id, price_version)
        raise
    _finish(executed.response, ctx, llms)
    result_id = await store_answer(
        sessions,
        executed,
        plan=plan,
        request=request,
        settings=settings,
        version=(prepared.version.data_timestamp, prepared.version.api_version),
    )
    await _record_usage(sessions, llms, ctx.trace_id, job_id, price_version)
    return result_id
