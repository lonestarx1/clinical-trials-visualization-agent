from collections.abc import Awaitable, Callable
from functools import partial
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.ctgov.client import CtgovClient, CtgovError, VersionInfo
from app.store.db import check_database

router = APIRouter(tags=["health"])

DatabaseCheck = Callable[[], Awaitable[bool]]
DataVersion = Callable[[], Awaitable[VersionInfo]]


class HealthChecks(BaseModel):
    database: Literal["ok", "error"] = Field(description="Postgres answers a query.")
    ctgov: Literal["ok", "error"] = Field(
        description="ClinicalTrials.gov answers its version endpoint. Reported only: it "
        "does not change `status`."
    )


class Health(BaseModel):
    status: Literal["ok", "unavailable"] = Field(
        description="`ok` when the database is reachable, else `unavailable` (with 503)."
    )
    checks: HealthChecks = Field(description="Result of each check.")
    data_timestamp: str | None = Field(  # ClinicalTrials.gov data version (cached /version)
        description="ClinicalTrials.gov data version; null when it cannot be reached.",
        examples=["2026-10-23T09:00:04"],
    )


async def _unavailable() -> bool:
    return False


async def _no_version() -> VersionInfo:
    raise CtgovError("no ClinicalTrials.gov client")


def get_database_check(request: Request) -> DatabaseCheck:
    engine = getattr(request.app.state, "engine", None)
    return partial(check_database, engine) if engine is not None else _unavailable


def get_data_version(request: Request) -> DataVersion:
    ctgov: CtgovClient | None = getattr(request.app.state, "ctgov", None)
    return ctgov.version if ctgov is not None else _no_version


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
