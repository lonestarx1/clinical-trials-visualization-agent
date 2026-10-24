"""Debug endpoint: run a hand-written QueryPlan without the AI stages.

Useful for checking the deterministic pipeline on its own. Disable with
ENABLE_DEBUG_ENDPOINTS=false.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_ctgov, get_settings
from app.core.config import Settings
from app.ctgov.client import CtgovClient
from app.pipeline.run import run_plan
from app.schemas.plan import QueryPlan
from app.schemas.response import QueryResponse

router = APIRouter(prefix="/v1/debug", tags=["debug"])


class DebugPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: QueryPlan
    citations_per_datum: int = Field(default=5, ge=1, le=50)


@router.post("/plan", response_model=QueryResponse)
async def run_debug_plan(
    body: DebugPlanRequest,
    ctgov: Annotated[CtgovClient, Depends(get_ctgov)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> QueryResponse:
    """Run a QueryPlan directly (no guard, no planner, no narrator)."""
    return await run_plan(
        body.plan,
        ctgov,
        base_url=settings.ctgov_base_url,
        citations_per_datum=body.citations_per_datum,
    )
