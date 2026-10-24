"""A small in-memory ClinicalTrials.gov for the mirror sync (design Q22).

It understands what the sync asks for: all trials, a `StartDate` range or `MISSING`, and a
`LastUpdatePostDate` range; counts (`pageSize=1`), pages of `pageSize` with page tokens, and
`/version`. Tests change `studies` and `data_timestamp` between syncs, like a daily update.
Search terms (`query.cond`, a phrase in `filter.advanced`, ...) match the NCT IDs that tests
put in `terms`, keyed like a term set ("query.cond|\"melanoma\""), ANDed with the rest.
"""

import re
from collections.abc import Callable
from typing import Any

import httpx

from app.ctgov.client import CtgovClient, RateLimiter
from tests.support.fakes import FakeClock, RecordingTransport, json_response

_RANGE = re.compile(r"AREA\[(\w+)\]RANGE\[([\w-]+),([\w-]+)\]")


def trial(nct: str, start: str | None = "2015-03", updated: str = "2026-10-01") -> dict[str, Any]:
    status: dict[str, Any] = {"lastUpdatePostDateStruct": {"date": updated}}
    if start:
        status["startDateStruct"] = {"date": start}
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": f"Trial {nct}"},
            "statusModule": status,
        }
    }


def _date(study: dict[str, Any], piece: str) -> str | None:
    status = study["protocolSection"]["statusModule"]
    struct = {"StartDate": "startDateStruct", "LastUpdatePostDate": "lastUpdatePostDateStruct"}
    value = status.get(struct[piece], {}).get("date")
    return None if value is None else (value + "-01")[:10]  # "2015-03" counts as 2015-03-01


class FakeRegistry:
    def __init__(self, studies: list[dict[str, Any]], data_timestamp: str) -> None:
        self.studies = {s["protocolSection"]["identificationModule"]["nctId"]: s for s in studies}
        self.data_timestamp = data_timestamp
        self.fail_after: int | None = None  # fail every /studies call after this many
        self.calls = 0
        self.on_version: list[Callable[[], None]] = []  # run one before each /version answer
        self.terms: dict[str, set[str]] = {}

    def put(self, *studies: dict[str, Any]) -> None:
        for s in studies:
            self.studies[s["protocolSection"]["identificationModule"]["nctId"]] = s

    def _term(self, key: str, found: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ids = self.terms[key]
        return [s for s in found if s["protocolSection"]["identificationModule"]["nctId"] in ids]

    def _clause(self, clause: str, found: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if clause == "AREA[StartDate]MISSING":
            return [s for s in found if _date(s, "StartDate") is None]
        match = _RANGE.fullmatch(clause)
        if match is None:
            return self._term(f"filter.advanced|{clause}", found)
        piece, lo, hi = match.groups()
        lo, hi = ("0000-00-00" if lo == "MIN" else lo), ("9999-99-99" if hi == "MAX" else hi)
        return [s for s in found if (d := _date(s, piece)) is not None and lo <= d <= hi]

    def _matching(self, params: httpx.QueryParams) -> list[dict[str, Any]]:
        found = sorted(self.studies.values(), key=lambda s: str(_date(s, "StartDate")))
        for param in ("query.cond", "query.intr", "query.lead", "query.spons"):
            if param in params:
                found = self._term(f"{param}|{params[param]}", found)
        advanced = params.get("filter.advanced", "")
        if advanced.startswith("(") and " AND " in advanced:  # a term narrowed by a date range
            clauses = advanced[1:-1].split(" AND ")
        else:
            clauses = [advanced] if advanced else []
        for clause in clauses:
            found = self._clause(clause, found)
        return found

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/version"):
            if self.on_version:
                self.on_version.pop(0)()
            return json_response({"apiVersion": "2.0.5", "dataTimestamp": self.data_timestamp})
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            return httpx.Response(400, text="the fake was told to fail")
        params = request.url.params
        found = self._matching(params)
        size = int(params["pageSize"])
        offset = int(params.get("pageToken", "0"))
        body: dict[str, Any] = {"studies": found[offset : offset + size]}
        if params.get("countTotal") == "true":
            body["totalCount"] = len(found)
        if size > 1 and offset + size < len(found):
            body["nextPageToken"] = str(offset + size)
        return json_response(body)

    def transport(self) -> RecordingTransport:
        return RecordingTransport(self.handle)


def registry_client(registry: FakeRegistry) -> tuple[CtgovClient, RecordingTransport]:
    """The real client against the fake, with no caching (like the sync's own client)."""
    clock = FakeClock()
    transport = registry.transport()
    client = CtgovClient(
        "https://clinicaltrials.gov/api/v2",
        http=httpx.AsyncClient(transport=transport),
        limiter=RateLimiter(6000, 4, clock=clock),
        clock=clock,
        max_attempts=1,
        version_ttl=0,
    )
    return client, transport
