from collections.abc import Awaitable, Callable
from functools import partial
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from app.ctgov.client import CtgovClient, CtgovError, VersionInfo
from app.store.db import check_database

router = APIRouter(tags=["health"])

DatabaseCheck = Callable[[], Awaitable[bool]]
DataVersion = Callable[[], Awaitable[VersionInfo]]


class HealthChecks(BaseModel):
    database: Literal["ok", "error"]
    ctgov: Literal["ok", "error"]


class Health(BaseModel):
    status: Literal["ok", "unavailable"]
    checks: HealthChecks
    data_timestamp: str | None  # ClinicalTrials.gov data version (cached /version)


def get_database_check(request: Request) -> DatabaseCheck:
    return partial(check_database, request.app.state.engine)


def get_data_version(request: Request) -> DataVersion:
    ctgov: CtgovClient = request.app.state.ctgov
    return ctgov.version


@router.get("/health", response_model=Health, responses={503: {"model": Health}})
async def health(
    response: Response,
    database_check: Annotated[DatabaseCheck, Depends(get_database_check)],
    data_version: Annotated[DataVersion, Depends(get_data_version)],
) -> Health:
    """Liveness and readiness. Used by the container healthcheck.

    Only the database decides the status: a ClinicalTrials.gov outage is reported
    here, and queries fail with their own error (Q17).
    """
    database_ok = await database_check()
    try:
        timestamp: str | None = (await data_version()).data_timestamp
    except CtgovError:
        timestamp = None
    if not database_ok:
        response.status_code = 503
    return Health(
        status="ok" if database_ok else "unavailable",
        checks=HealthChecks(
            database="ok" if database_ok else "error",
            ctgov="ok" if timestamp else "error",
        ),
        data_timestamp=timestamp,
    )
