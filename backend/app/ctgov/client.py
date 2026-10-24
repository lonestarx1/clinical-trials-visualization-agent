"""Async client for the ClinicalTrials.gov API v2 (design Q6, Q8).

All calls share one rate limiter (requests per minute, a burst, max in flight).
Retries 429/5xx/timeouts/connection errors with capped, jittered exponential
backoff and Retry-After (a 429 without one waits `throttle_wait`); never retries
400/404. A circuit breaker fails fast after repeated failures.
"""

import asyncio
import json
import logging
import random
import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol

import httpx

from app.ctgov.compiler import Search

log = logging.getLogger(__name__)

PAGE_SIZE = 1000
COUNT_CACHE_SIZE = 4096
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
    """At most `per_minute` request starts per minute and `concurrency` in flight.

    Up to `burst` requests may start at once: at most `burst` starts in any window of
    `burst * 60 / per_minute` seconds (a sliding window). `burst=1` spaces every start evenly.
    """

    def __init__(
        self,
        per_minute: int,
        concurrency: int,
        clock: ClockLike | None = None,
        *,
        burst: int = 1,
    ) -> None:
        self._window = burst * 60.0 / per_minute
        self._starts: deque[float] = deque(maxlen=burst)
        self._slots = asyncio.Semaphore(concurrency)
        self._lock = asyncio.Lock()
        self._clock = clock or _SystemClock()

    async def __aenter__(self) -> None:
        await self._slots.acquire()
        try:
            async with self._lock:
                start = self._clock.monotonic()
                if len(self._starts) == self._starts.maxlen:
                    free_at = self._starts[0] + self._window
                    if free_at > start:
                        await self._clock.sleep(free_at - start)
                    start = max(free_at, self._clock.monotonic())
                self._starts.append(start)
        except BaseException:  # cancelled while waiting its turn (a cancelled job): no __aexit__
            self._slots.release()
            raise

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
        throttle_wait: float = 10.0,
        count_ttl: float = 0.0,
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
        self._throttle_wait = throttle_wait
        self._count_ttl = count_ttl
        self._counts: OrderedDict[str, tuple[float, int]] = OrderedDict()  # params -> (at, count)
        self._version: tuple[float, VersionInfo] | None = None

    # ---------- public API ----------

    async def count(self, search: Search) -> int:
        """Number of studies matching the search (one cheap call).

        Kept for `count_ttl` seconds (0: not kept), and dropped when the data timestamp changes.
        """
        key = json.dumps(search.params, sort_keys=True)
        cached = self._counts.get(key)
        if cached and self._clock.monotonic() - cached[0] < self._count_ttl:
            self._counts.move_to_end(key)
            return cached[1]
        body = await self._get(
            "/studies", search.params | {"countTotal": "true", "pageSize": "1", "fields": "NCTId"}
        )
        total = int(body["totalCount"])
        if self._count_ttl > 0:
            self._counts[key] = (self._clock.monotonic(), total)
            self._counts.move_to_end(key)
            if len(self._counts) > COUNT_CACHE_SIZE:
                self._counts.popitem(last=False)
        return total

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

    async def first_page(
        self, search: Search, fields: Sequence[str], size: int, sort: str | None = None
    ) -> list[dict[str, Any]]:
        """The first `size` matching studies (sample citations), optionally sorted."""
        params = search.params | {"fields": ",".join(fields), "pageSize": str(size)}
        if sort:
            params["sort"] = sort
        body = await self._get("/studies", params)
        return list(body.get("studies", []))

    async def version(self) -> VersionInfo:
        """API version and data timestamp, cached for `version_ttl` seconds."""
        now = self._clock.monotonic()
        if self._version and now - self._version[0] < self._version_ttl:
            return self._version[1]
        body = await self._get("/version", {})
        info = VersionInfo(body["apiVersion"], body["dataTimestamp"])
        if self._version and self._version[1].data_timestamp != info.data_timestamp:
            self._counts.clear()  # the daily update: every count may have changed
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
                if retry_after is None and response.status_code == 429:
                    retry_after = self._throttle_wait  # no header: wait out the rate window

            if attempt + 1 < self._max_attempts:
                delay = retry_after
                if delay is None:
                    delay = self._jitter(min(self._backoff_cap, self._backoff_base * 2**attempt))
                log.info("retrying %s after %s (attempt %d)", path, problem, attempt + 1)
                await self._clock.sleep(delay)
        raise CtgovUnavailable(f"{path} failed after {self._max_attempts} attempts: {problem}")
