"""A fake ClinicalTrials.gov that serves the recorded studies through the real client."""

from collections.abc import Callable

import httpx

from app.ctgov.client import CtgovClient, RateLimiter
from tests.support.fakes import FakeClock, RecordingTransport, json_response
from tests.support.samples import load_sample, sample_names

BASE = "https://clinicaltrials.gov/api/v2"
VERSION = {"apiVersion": "2.0.5", "dataTimestamp": "2026-10-23T09:00:04"}


def recorded_handler(
    matches: Callable[[httpx.Request], bool] = lambda _: True,
) -> Callable[[httpx.Request], httpx.Response]:
    """Every search returns all recorded studies, or none when `matches` says so."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/version"):
            return json_response(VERSION)
        studies = [load_sample(n) for n in sample_names()] if matches(request) else []
        if request.url.params.get("pageSize") == "1":
            return json_response({"studies": studies[:1], "totalCount": len(studies)})
        return json_response({"studies": studies, "totalCount": len(studies)})

    return handler


def recorded_client(
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
) -> tuple[CtgovClient, RecordingTransport]:
    clock = FakeClock()
    transport = RecordingTransport(handler or recorded_handler())
    client = CtgovClient(
        BASE,
        http=httpx.AsyncClient(transport=transport),
        limiter=RateLimiter(6000, 2, clock=clock),
        clock=clock,
        max_attempts=1,
    )
    return client, transport
