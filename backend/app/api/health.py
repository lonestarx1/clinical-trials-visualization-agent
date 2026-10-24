from collections.abc import Awaitable, Callable
from functools import partial
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.openapi import HEALTH_RESPONSES
from app.ctgov.client import CtgovClient, CtgovError, VersionInfo
from app.mirror.fast import mirror_status
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


class FastMode(BaseModel):
    status: Literal["ready", "syncing", "not_loaded", "off", "unknown"] = Field(
        description='`ready`: `mode: "fast"` can answer from our copy of ClinicalTrials.gov. '
        "`syncing`: our copy is catching up with a new update (fast requests are answered live "
        "meanwhile). `not_loaded`: the first load hasn't finished. `off`: fast mode is turned off "
        "on this server. `unknown`: ClinicalTrials.gov can't be reached to compare."
    )
    data_timestamp: str | None = Field(
        default=None,
        description="The ClinicalTrials.gov data version our copy holds.",
        examples=["2026-10-23T09:00:04"],
    )


FastStatus = Callable[[str | None], Awaitable[FastMode]]


class Health(BaseModel):
    status: Literal["ok", "unavailable"] = Field(
        description="`ok` when the database is reachable, else `unavailable` (with 503)."
    )
    checks: HealthChecks = Field(description="Result of each check.")
    data_timestamp: str | None = Field(  # ClinicalTrials.gov data version (cached /version)
        description="ClinicalTrials.gov data version; null when it cannot be reached.",
        examples=["2026-10-23T09:00:04"],
    )
    fast_mode: FastMode = Field(description="Whether fast mode can answer now (design Q22).")


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


def get_fast_status(request: Request) -> FastStatus:
    settings = getattr(request.app.state, "settings", None)
    sessions = getattr(request.app.state, "sessions", None)

    async def status(current: str | None) -> FastMode:
        if settings is None or not settings.fast_mode_enabled or sessions is None:
            return FastMode(status="off")
        if current is None:
            return FastMode(status="unknown")
        try:
            state, held = await mirror_status(sessions, current)
        except Exception:  # the database is down: the status says so already
            return FastMode(status="unknown")
        return FastMode(status=state, data_timestamp=held)

    return status


@router.get(
    "/health",
    response_model=Health,
    summary="Liveness and readiness",
    description="Checks the database and ClinicalTrials.gov and reports the "
    "ClinicalTrials.gov data version. Only the database decides the status (503 when it is "
    "unreachable); a ClinicalTrials.gov outage is reported in `checks`, and questions then "
    "fail with `503 upstream_unavailable`. Not rate limited.",
    responses={**HEALTH_RESPONSES, 503: HEALTH_RESPONSES[503] | {"model": Health}},
)
async def health(
    response: Response,
    database_check: Annotated[DatabaseCheck, Depends(get_database_check)],
    data_version: Annotated[DataVersion, Depends(get_data_version)],
    fast_status: Annotated[FastStatus, Depends(get_fast_status)],
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
        fast_mode=await fast_status(timestamp),
    )
