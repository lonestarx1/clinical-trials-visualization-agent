from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_ctgov, get_llm_factory, get_settings
from app.core.config import Settings
from app.ctgov.client import CtgovClient
from app.llm.client import UsageLog
from app.pipeline.query import LLMFactory, handle_query
from app.schemas.request import QueryRequest
from app.schemas.response import QueryResponse

router = APIRouter(prefix="/v1", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query(
    body: QueryRequest,
    ctgov: Annotated[CtgovClient, Depends(get_ctgov)],
    llm_factory: Annotated[LLMFactory, Depends(get_llm_factory)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> QueryResponse:
    """Turn a question (plus optional fields) into a visualization spec with citations."""
    return await handle_query(body, ctgov=ctgov, llms=llm_factory(UsageLog()), settings=settings)
