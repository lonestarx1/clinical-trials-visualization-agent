import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_sessions, get_settings
from app.core.config import Settings
from app.ctgov.countries import CANONICAL
from app.registry import DIMENSIONS, MEASURES, ChartType
from app.registry.enums import Phase, Status
from app.store import jobs, results, usage
from app.store.models import Result
from app.store.results import NotFound

router = APIRouter(prefix="/v1", tags=["results"])
Sessions = Annotated[async_sessionmaker[AsyncSession] | None, Depends(get_sessions)]


def _need(sessions: async_sessionmaker[AsyncSession] | None) -> async_sessionmaker[AsyncSession]:
    if sessions is None:
        raise NotFound("results are not stored in this deployment")
    return sessions


@router.get("/results/{result_id}/citations")
async def citations(
    result_id: uuid.UUID,
    sessions: Sessions,
    datum: Annotated[str, Query(description="The data point's `key`")],
    cursor: Annotated[
        int | None, Query(ge=0, description="`next_cursor` from the previous page")
    ] = None,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    """Every trial behind one data point, in citation order, paginated (design Q14)."""
    async with _need(sessions)() as s:
        page = await results.citation_page(s, result_id, datum, after=cursor, limit=page_size)
    return {
        "result_id": str(page.result_id),
        "datum": page.datum_key,
        "label": page.label,
        "citation_count": page.citation_count,
        "citations": page.citations,
        "next_cursor": page.next_cursor,
    }


@router.get("/jobs/{job_id}")
async def job_status(job_id: uuid.UUID, sessions: Sessions) -> dict[str, Any]:
    """Poll a background job (design Q6)."""
    async with _need(sessions)() as s:
        job = await jobs.get(s, job_id)
        if job is None:
            raise NotFound(f"no job {job_id}")
        result = None
        if job.result_id is not None:
            stored = await s.get(Result, job.result_id)
            result = stored.response if stored else None
    return {
        "job_id": str(job.job_id),
        "status": job.status,
        "progress": job.progress,
        "estimated_seconds": job.estimated_seconds,
        "result": result,
        "error": job.error if job.status == "failed" else None,
    }


@router.get("/options")
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


@router.get("/usage")
async def usage_today(
    sessions: Sessions,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Today's LLM calls and cost (admin token required)."""
    token = settings.admin_token.get_secret_value() if settings.admin_token else None
    if not token or authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="admin token required")
    from datetime import UTC, datetime

    async with _need(sessions)() as s:
        summary = await usage.summary(s, day=datetime.now(UTC).date())
    return summary | {"budget_usd": settings.llm_daily_budget_usd}
