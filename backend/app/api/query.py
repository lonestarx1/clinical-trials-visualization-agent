from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import client_ip, get_ctgov, get_llm_factory, get_sessions, get_settings
from app.core.config import Settings
from app.ctgov.client import CtgovClient
from app.llm.client import UsageLog
from app.pipeline.query import JobAccepted, LLMFactory, handle_query
from app.schemas.request import QueryRequest
from app.schemas.response import QueryResponse

router = APIRouter(prefix="/v1", tags=["query"])

ACCEPTED: dict[int | str, dict[str, Any]] = {
    202: {"description": "Broad question: running as a background job; poll `poll_url`."}
}


@router.post("/query", response_model=QueryResponse, responses=ACCEPTED)
async def query(
    body: QueryRequest,
    request: Request,
    ctgov: Annotated[CtgovClient, Depends(get_ctgov)],
    llm_factory: Annotated[LLMFactory, Depends(get_llm_factory)],
    settings: Annotated[Settings, Depends(get_settings)],
    sessions: Annotated[async_sessionmaker[AsyncSession] | None, Depends(get_sessions)],
) -> QueryResponse | JSONResponse:
    """Turn a question (plus optional fields) into a visualization spec with citations."""
    pricing = getattr(request.app.state, "pricing", None)
    outcome = await handle_query(
        body,
        ctgov=ctgov,
        llms=llm_factory(UsageLog()),
        settings=settings,
        sessions=sessions,
        client_ip=client_ip(request),
        price_version=str(pricing.version) if pricing else "1",
    )
    if isinstance(outcome, JobAccepted):
        return JSONResponse(
            status_code=202,
            content={
                "job_id": str(outcome.job_id),
                "status": "pending",
                "poll_url": f"/v1/jobs/{outcome.job_id}",
                "estimated_seconds": outcome.estimated_seconds,
            },
        )
    return outcome
