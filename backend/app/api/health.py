from collections.abc import Awaitable, Callable
from functools import partial
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from app.store.db import check_database

router = APIRouter(tags=["health"])

DatabaseCheck = Callable[[], Awaitable[bool]]


class HealthChecks(BaseModel):
    database: Literal["ok", "error"]


class Health(BaseModel):
    status: Literal["ok", "unavailable"]
    checks: HealthChecks


def get_database_check(request: Request) -> DatabaseCheck:
    return partial(check_database, request.app.state.engine)


@router.get("/health", response_model=Health, responses={503: {"model": Health}})
async def health(
    response: Response,
    database_check: Annotated[DatabaseCheck, Depends(get_database_check)],
) -> Health:
    """Liveness and readiness. Used by the container healthcheck."""
    database_ok = await database_check()
    if not database_ok:
        response.status_code = 503
    return Health(
        status="ok" if database_ok else "unavailable",
        checks=HealthChecks(database="ok" if database_ok else "error"),
    )
