from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api import examples
from app.api.deps import client_ip, get_ctgov, get_llm_factory, get_sessions, get_settings
from app.api.openapi import QUERY_RESPONSES
from app.core.config import Settings
from app.ctgov.client import CtgovClient
from app.llm.client import UsageLog
from app.pipeline.query import JobAccepted, LLMFactory, handle_query
from app.schemas.request import QueryRequest
from app.schemas.response import QueryResponse

router = APIRouter(prefix="/v1", tags=["query"])

DESCRIPTION = """
Runs the question through the input guard and the planning agent (in parallel), checks the
plan, fetches the matching trials from ClinicalTrials.gov, aggregates them, verifies every
citation against the trial records, and has the narrator write the title.

- **Fields override the AI.** `drug_name`, `condition`, `sponsor`, `country`, `trial_phase`,
  `status`, the years, `compare`, `chart_type` and the options are applied as given, even when
  the question says otherwise; a conflict is noted in `meta.warnings`.
- **200** is an answer: a chart (`status: ok`) or the reason there is none
  (`no_matching_trials`, `out_of_scope`, `could_not_interpret`).
- **202** means the question is broad (its retrieval is estimated at over a minute) and runs
  as a background job: poll `poll_url`. The same question while its job is active returns
  the same job.
- Each data point inlines up to `citations_per_datum` citations; page through all of them
  with `GET /v1/results/{result_id}/citations?datum=<key>`.
- Repeated questions reuse the cached plan and, if ClinicalTrials.gov data has not changed,
  the stored result (`meta.cache`).
"""


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Ask a question, get a chart specification",
    description=DESCRIPTION,
    responses=QUERY_RESPONSES,
)
async def query(
    body: Annotated[QueryRequest, Body(openapi_examples=examples.QUERY_REQUESTS)],
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
