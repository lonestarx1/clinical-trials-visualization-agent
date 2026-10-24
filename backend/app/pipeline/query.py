"""Answer a question (design Q2): guard ∥ planner -> gate -> pipeline -> narrator."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from app.agents.guard import check_request
from app.agents.narrator import narrate
from app.agents.planner import plan_request
from app.core.config import Settings
from app.ctgov.client import CtgovClient
from app.llm.client import LLM, UsageLog
from app.pipeline.run import run_plan
from app.schemas.request import QueryRequest
from app.schemas.response import Meta, QueryResponse

log = logging.getLogger(__name__)


class RejectedByPolicy(Exception):
    """The guard classified the request as malicious (400). The reason is logged only."""


@dataclass
class StageLLMs:
    guard: LLM
    planner: LLM
    narrator: LLM

    def usage(self) -> UsageLog:
        logs = {id(m.usage): m.usage for m in (self.guard, self.planner, self.narrator)}
        return UsageLog([c for usage in logs.values() for c in usage.calls])


LLMFactory = Callable[[UsageLog], StageLLMs]


async def handle_query(
    request: QueryRequest, *, ctgov: CtgovClient, llms: StageLLMs, settings: Settings
) -> QueryResponse:
    guard_task = asyncio.create_task(check_request(llms.guard, request))
    plan_task = asyncio.create_task(
        plan_request(llms.planner, request, ctgov, max_steps=settings.planner.max_steps)
    )
    try:
        verdict = await guard_task
    except BaseException:
        plan_task.cancel()
        raise
    if verdict.verdict == "malicious":
        plan_task.cancel()
        log.info("rejected by guard: %s", verdict.reason)
        raise RejectedByPolicy
    planned = await plan_task

    guard_meta = {"verdict": verdict.verdict, "model": verdict.model}
    planner_meta = {
        "steps": planned.steps,
        "tool_calls": planned.tool_calls,
        "model": planned.model,
    }

    if planned.plan is None:
        meta = Meta(
            guard=guard_meta,
            planner=planner_meta,
            usage=llms.usage().summary(),
            details={"errors": planned.errors, "best_attempt": planned.best_attempt},
        )
        return QueryResponse(status="could_not_interpret", visualization=None, meta=meta)
    plan = planned.plan
    if plan.scope == "out_of_scope":
        meta = Meta(
            guard=guard_meta,
            planner=planner_meta,
            usage=llms.usage().summary(),
            assumptions=plan.assumptions,
            details={"reason": plan.scope_reason},
        )
        return QueryResponse(status="out_of_scope", visualization=None, meta=meta)

    response = await run_plan(
        plan,
        ctgov,
        base_url=settings.ctgov_base_url,
        citations_per_datum=request.citations_per_datum,
        narrator=partial(narrate, llms.narrator),
    )
    meta = response.meta
    meta.guard, meta.planner = guard_meta, planner_meta
    meta.warnings = planned.warnings + meta.warnings
    if meta.interpretation is not None:
        meta.interpretation.chart_type_source = planned.chart_type_source  # type: ignore[assignment]
    meta.usage = llms.usage().summary()
    return response
