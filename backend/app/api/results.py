import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_ctgov, get_sessions, get_settings
from app.api.openapi import (
    CANCEL_RESPONSES,
    CITATION_RESPONSES,
    JOB_RESPONSES,
    OPTIONS_RESPONSES,
    USAGE_RESPONSES,
)
from app.core.config import Settings
from app.ctgov.client import CtgovClient
from app.ctgov.countries import CANONICAL
from app.pipeline.citations import source_pages
from app.registry import DIMENSIONS, MEASURES, ChartType
from app.registry.enums import Phase, Status
from app.store import jobs, results, usage
from app.store.models import Job, Result
from app.store.results import NotFound

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1")
JobId = Annotated[uuid.UUID, Path(description="`job_id` from the 202 response.")]
Sessions = Annotated[async_sessionmaker[AsyncSession] | None, Depends(get_sessions)]


def _need(sessions: async_sessionmaker[AsyncSession] | None) -> async_sessionmaker[AsyncSession]:
    if sessions is None:
        raise NotFound("results are not stored in this deployment")
    return sessions


@router.get(
    "/results/{result_id}/citations",
    response_model=None,  # the body is a dict; CitationPage documents it
    tags=["citations"],
    summary="List every trial behind one data point",
    description="Every trial that contributes to one data point (bar, bucket, node, edge...) "
    "of a stored result, in the same order as its inline citations, keyset-paginated. Use "
    "the response's `result_id` and the data point's `key`; follow `next_cursor` until it "
    "is null. Each citation has the `evidence`: the trial record fields that place it in "
    "the data point. A data point counted without reading every trial (trials per year "
    "on a broad question) lists the rest from ClinicalTrials.gov as you page, so a page "
    "can take a few seconds the first time. Results are kept for 24 hours.",
    responses=CITATION_RESPONSES,
)
async def citations(
    result_id: Annotated[uuid.UUID, Path(description="`result_id` from the query response.")],
    sessions: Sessions,
    ctgov: Annotated[CtgovClient, Depends(get_ctgov)],
    datum: Annotated[
        str, Query(description="The data point's `key`, e.g. `PHASE2` or `drug:nivolumab`.")
    ],
    cursor: Annotated[
        int | None,
        Query(ge=0, description="`next_cursor` from the previous page; omit for the first."),
    ] = None,
    page_size: Annotated[int, Query(ge=1, le=100, description="Citations per page.")] = 50,
) -> dict[str, Any]:
    """Every trial behind one data point, in citation order, paginated (design Q14)."""
    async with _need(sessions)() as s:
        upto = (cursor or 0) + page_size + 1  # one more, to know whether a next page exists
        await results.extend_citations(s, result_id, datum, upto=upto, fetch=source_pages(ctgov))
        await s.commit()
        page = await results.citation_page(s, result_id, datum, after=cursor, limit=page_size)
    return {
        "result_id": str(page.result_id),
        "datum": page.datum_key,
        "label": page.label,
        "citation_count": page.citation_count,
        "citations": page.citations,
        "next_cursor": page.next_cursor,
    }


@router.get(
    "/jobs/{job_id}",
    response_model=None,  # the body is a dict; JobStatus documents it
    tags=["jobs"],
    summary="Poll a background job",
    description="Status of the background job started by a broad question (`202` from "
    "`POST /v1/query`). Poll every few seconds: `pending` and `running` report `progress` "
    "in ClinicalTrials.gov pages; `succeeded` carries the normal query response in "
    "`result`; `failed` carries the shared error body in `error`, and so does `cancelled` "
    "(code `cancelled`, after `DELETE`). A job that crashed is retried before it is "
    "marked failed. A finished job is kept for 24 hours, like its "
    "result; after that, polling returns `410 expired`.",
    responses=JOB_RESPONSES,
)
async def job_status(job_id: JobId, sessions: Sessions) -> dict[str, Any]:
    """Poll a background job (design Q6)."""
    async with _need(sessions)() as s:
        job, stored = await jobs.get_live(s, job_id)
    return _job_body(job, stored)


@router.delete(
    "/jobs/{job_id}",
    response_model=None,  # the body is a dict; JobStatus documents it
    tags=["jobs"],
    summary="Cancel a background job",
    description="Stops a `pending` or `running` job: its status becomes `cancelled` (with "
    "`error.code` `cancelled`) and the worker stops within about a second, before its next "
    "ClinicalTrials.gov page. Returns the job as polling would. A job that has already "
    "finished (`succeeded`, `failed` or `cancelled`) is returned unchanged, so repeating "
    "the call is safe. Anyone holding the `job_id` can cancel the job, as anyone holding it "
    "can poll it: the id is a random UUID returned only to the client that asked. Asking "
    "the same question again afterwards starts a new job.",
    responses=CANCEL_RESPONSES,
)
async def cancel_job(job_id: JobId, sessions: Sessions) -> dict[str, Any]:
    """Cancel a background job; idempotent (design Q6)."""
    async with _need(sessions)() as s:
        if await jobs.cancel(s, job_id):
            log.info("job %s cancelled by the client", job_id)
        await s.commit()
        job, stored = await jobs.get_live(s, job_id)
    return _job_body(job, stored)


def _job_body(job: Job, stored: Result | None) -> dict[str, Any]:
    return {
        "job_id": str(job.job_id),
        "status": job.status,
        "progress": job.progress,
        "estimated_seconds": job.estimated_seconds,
        "result": stored.response if stored else None,
        "error": job.error if job.status in ("failed", "cancelled") else None,
    }


@router.get(
    "/options",
    response_model=None,  # the body is a dict; Options documents it
    tags=["options"],
    summary="List dimensions, measures, chart types and filter values",
    description="The registry the planner works from, so a client can build pickers: "
    "dimensions (what data can be grouped by, with their counting rules and, for "
    "categorical ones, their values and labels), measures, chart types, and the values the "
    "`trial_phase`, `status` and `country` fields accept.",
    responses=OPTIONS_RESPONSES,
)
async def options() -> dict[str, Any]:
    """The registry, so a frontend can build pickers: dimensions, measures, chart types, filters."""
    return {
        "dimensions": [
            {
                "key": d.key,
                "label": d.label,
                "kind": d.kind.value,
                "multi_valued": d.multi_valued,
                "counting_rule": d.counting_rule,
                "values": [{"value": m.value, "label": m.label} for m in d.enum]
                if d.enum
                else None,
            }
            for d in DIMENSIONS.values()
        ],
        "measures": [{"key": m.key, "label": m.label, "unit": m.unit} for m in MEASURES.values()],
        "chart_types": [{"key": c.value} for c in ChartType],
        "filters": {
            "trial_phase": [{"value": p.value, "label": p.label} for p in Phase],
            "status": [{"value": s.value, "label": s.label} for s in Status],
            "country": list(CANONICAL),
        },
    }


@router.get(
    "/usage",
    response_model=None,  # the body is a dict; UsageSummary documents it
    tags=["admin"],
    summary="Today's AI usage and cost",
    description="AI calls and cost so far today (UTC day), per model, with the daily budget. "
    "Needs `Authorization: Bearer <ADMIN_TOKEN>`; without `ADMIN_TOKEN` configured the "
    "endpoint always answers 401.",
    responses=USAGE_RESPONSES,
)
async def usage_today(
    sessions: Sessions,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header(description="`Bearer <ADMIN_TOKEN>`.")] = None,
) -> dict[str, Any]:
    """Today's LLM calls and cost (admin token required)."""
    token = settings.admin_token.get_secret_value() if settings.admin_token else None
    if not token or authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="admin token required")
    from datetime import UTC, datetime

    async with _need(sessions)() as s:
        summary = await usage.summary(s, day=datetime.now(UTC).date())
    return summary | {"budget_usd": settings.llm_daily_budget_usd}
