"""Async client for the ClinicalTrials.gov API v2 (design Q6, Q8).

All calls share one rate limiter (requests per minute + max in flight).
Retries 429/5xx/timeouts/connection errors with capped, jittered exponential
backoff and Retry-After; never retries 400/404. A circuit breaker fails fast
after repeated failures.
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol

import httpx

from app.ctgov.compiler import Search

log = logging.getLogger(__name__)

PAGE_SIZE = 1000
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ClockLike(Protocol):
    """The clock used by the limiter and the client: real, or fake in tests."""

    def monotonic(self) -> float: ...
    async def sleep(self, seconds: float) -> None: ...


class _SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class CtgovError(Exception):
    pass


class CtgovBadRequest(CtgovError):
    """400/404: our query is wrong or the resource doesn't exist. Not retried."""


class CtgovUnavailable(CtgovError):
    """Retries exhausted."""


class CircuitOpen(CtgovUnavailable):
    """Too many recent failures: failing fast instead of adding load."""


class InconsistentResults(CtgovError):
    """The fetched trials don't match the reported total (data changed mid-fetch?)."""


class RateLimiter:
    """At most `per_minute` request starts per minute and `concurrency` in flight."""

    def __init__(self, per_minute: int, concurrency: int, clock: ClockLike | None = None) -> None:
        self._interval = 60.0 / per_minute
        self._slots = asyncio.Semaphore(concurrency)
        self._lock = asyncio.Lock()
        self._next_start = 0.0
        self._clock = clock or _SystemClock()

    async def __aenter__(self) -> None:
        await self._slots.acquire()
        async with self._lock:
            wait = self._next_start - self._clock.monotonic()
            if wait > 0:
                await self._clock.sleep(wait)
            self._next_start = max(self._next_start, self._clock.monotonic()) + self._interval

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._slots.release()


@dataclass(frozen=True)
class FetchResult:
    studies: list[dict[str, Any]]
    total_count: int


@dataclass(frozen=True)
class VersionInfo:
    api_version: str
    data_timestamp: str


def _nct_id(study: dict[str, Any]) -> str:
    return str(study["protocolSection"]["identificationModule"]["nctId"])


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return float(response.headers["Retry-After"])
    except (KeyError, ValueError):
        return None


class CtgovClient:
    def __init__(
        self,
        base_url: str,
        http: httpx.AsyncClient,
        limiter: RateLimiter,
        *,
        clock: ClockLike | None = None,
        max_attempts: int = 4,
        backoff_base: float = 1.0,
        backoff_cap: float = 30.0,
        jitter: Callable[[float], float] = lambda upper: random.uniform(0, upper),
        breaker_threshold: int = 5,
        breaker_cooldown: float = 30.0,
        version_ttl: float = 600.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._http = http
        self._limiter = limiter
        self._clock = clock or _SystemClock()
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._jitter = jitter
        self._breaker_threshold = breaker_threshold
        self._breaker_cooldown = breaker_cooldown
        self._failures = 0
        self._open_until = 0.0
        self._version_ttl = version_ttl
        self._version: tuple[float, VersionInfo] | None = None

    # ---------- public API ----------

    async def count(self, search: Search) -> int:
        """Number of studies matching the search (one cheap call)."""
        body = await self._get(
            "/studies", search.params | {"countTotal": "true", "pageSize": "1", "fields": "NCTId"}
        )
        return int(body["totalCount"])

    async def fetch_all(
        self,
        search: Search,
        fields: Sequence[str],
        on_page: Callable[[int], Awaitable[None]] | None = None,
    ) -> FetchResult:
        """Every matching study with only `fields`, following page tokens.

        `on_page(pages_done)` is awaited after each page (job progress).
        """
        params = search.params | {"fields": ",".join(fields), "pageSize": str(PAGE_SIZE)}
        body = await self._get("/studies", params | {"countTotal": "true"})
        total = int(body["totalCount"])
        studies: dict[str, dict[str, Any]] = {}
        pages = 0
        while True:
            pages += 1
            if on_page is not None:
                await on_page(pages)
            for study in body.get("studies", []):
                studies.setdefault(_nct_id(study), study)
            token = body.get("nextPageToken")
            if not token:  # an empty page with a token is not the end
                break
            body = await self._get("/studies", params | {"pageToken": token})
        if len(studies) != total:
            raise InconsistentResults(
                f"fetched {len(studies)} distinct trials but the API reported {total}"
            )
        return FetchResult(list(studies.values()), total)

    async def version(self) -> VersionInfo:
        """API version and data timestamp, cached for `version_ttl` seconds."""
        now = self._clock.monotonic()
        if self._version and now - self._version[0] < self._version_ttl:
            return self._version[1]
        body = await self._get("/version", {})
        info = VersionInfo(body["apiVersion"], body["dataTimestamp"])
        self._version = (now, info)
        return info

    # ---------- transport ----------

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if self._clock.monotonic() < self._open_until:
            raise CircuitOpen("ClinicalTrials.gov is failing; not sending requests for now")
        try:
            body = await self._get_with_retries(path, params)
        except CtgovUnavailable:
            self._failures += 1
            if self._failures >= self._breaker_threshold:
                self._open_until = self._clock.monotonic() + self._breaker_cooldown
                log.warning("circuit opened after %d consecutive failures", self._failures)
            raise
        self._failures = 0
        return body

    async def _get_with_retries(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        problem = "no attempt made"
        for attempt in range(self._max_attempts):
            retry_after = None
            try:
                async with self._limiter:
                    response = await self._http.get(f"{self._base}{path}", params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                problem = f"{type(exc).__name__}"
            else:
                if response.status_code == 200:
                    result: dict[str, Any] = response.json()
                    return result
                if response.status_code not in RETRYABLE_STATUS:
                    raise CtgovBadRequest(f"HTTP {response.status_code}: {response.text[:300]}")
                problem = f"HTTP {response.status_code}"
                retry_after = _retry_after(response)

            if attempt + 1 < self._max_attempts:
                delay = retry_after
                if delay is None:
                    delay = self._jitter(min(self._backoff_cap, self._backoff_base * 2**attempt))
                log.info("retrying %s after %s (attempt %d)", path, problem, attempt + 1)
                await self._clock.sleep(delay)
        raise CtgovUnavailable(f"{path} failed after {self._max_attempts} attempts: {problem}")
