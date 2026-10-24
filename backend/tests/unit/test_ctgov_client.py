"""ClinicalTrials.gov client (design Q8): rate limit, retries, circuit breaker, paging."""

import asyncio
from typing import Any

import httpx
import pytest

from app.ctgov.client import (
    CircuitOpen,
    CtgovBadRequest,
    CtgovClient,
    CtgovUnavailable,
    InconsistentResults,
    RateLimiter,
)
from app.ctgov.compiler import Search
from tests.support.fakes import FakeClock, RecordingTransport, json_response, sequence

BASE = "https://clinicaltrials.gov/api/v2"
SEARCH = Search({"query.cond": '"melanoma"'})


def make_client(
    handler: Any, clock: FakeClock, **kwargs: Any
) -> tuple[CtgovClient, RecordingTransport]:
    transport = RecordingTransport(handler)
    client = CtgovClient(
        BASE,
        http=httpx.AsyncClient(transport=transport),
        limiter=kwargs.pop("limiter", RateLimiter(6000, 2, clock=clock)),
        clock=clock,
        jitter=lambda upper: upper,  # deterministic: always the maximum backoff
        **kwargs,
    )
    return client, transport


# ---------- rate limiter ----------


async def test_limiter_spaces_request_starts() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, concurrency=2, clock=clock)
    starts = []
    for _ in range(3):
        async with limiter:
            starts.append(clock.now)
    assert starts == [0.0, 1.0, 2.0]


async def test_limiter_lets_a_burst_start_at_once_then_keeps_the_rate() -> None:
    """ClinicalTrials.gov counts requests per ~10 s window, so a burst needn't be spaced out."""
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, concurrency=10, clock=clock, burst=3)
    starts = []
    for _ in range(7):
        async with limiter:
            starts.append(clock.now)
    # At most 3 starts in any 3 s window: 60 a minute on average.
    assert starts == [0.0, 0.0, 0.0, 3.0, 3.0, 3.0, 6.0]


async def test_limiter_burst_refills_after_a_quiet_spell() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, concurrency=10, clock=clock, burst=3)
    for _ in range(3):
        async with limiter:
            pass
    clock.now += 2.5
    starts = []
    for _ in range(3):
        async with limiter:
            starts.append(clock.now)
    assert starts == [3.0, 3.0, 3.0]


async def test_limiter_caps_concurrency() -> None:
    limiter = RateLimiter(per_minute=60_000, concurrency=2)
    in_flight = peak = 0

    async def work() -> None:
        nonlocal in_flight, peak
        async with limiter:
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1

    await asyncio.gather(*(work() for _ in range(6)))
    assert peak == 2


async def test_a_request_cancelled_while_waiting_its_turn_gives_its_slot_back() -> None:
    """Cancelling a job cancels requests queued in the shared limiter; none may keep a slot."""
    limiter = RateLimiter(per_minute=60, concurrency=1)  # one start per second

    async def request() -> None:
        async with limiter:
            pass

    await request()  # the next start is now a second away
    waiting = asyncio.create_task(request())
    await asyncio.sleep(0.05)  # holds the only slot, sleeping until its start time
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    await asyncio.wait_for(request(), timeout=2)  # would hang if the slot had leaked


# ---------- count ----------


async def test_count_asks_for_one_minimal_record() -> None:
    clock = FakeClock()
    client, transport = make_client(
        sequence(json_response({"studies": [{}], "totalCount": 812})), clock
    )
    assert await client.count(SEARCH) == 812
    params = transport.requests[0].url.params
    assert transport.requests[0].url.path == "/api/v2/studies"
    assert params["query.cond"] == '"melanoma"'
    assert (params["countTotal"], params["pageSize"], params["fields"]) == ("true", "1", "NCTId")


# ---------- retries ----------


async def test_retries_server_errors_with_backoff() -> None:
    clock = FakeClock()
    handler = sequence(
        httpx.Response(503), httpx.Response(502), json_response({"studies": [], "totalCount": 3})
    )
    client, transport = make_client(handler, clock)
    assert await client.count(SEARCH) == 3
    assert len(transport.requests) == 3
    assert clock.sleeps == [1.0, 2.0]


async def test_honours_retry_after() -> None:
    clock = FakeClock()
    handler = sequence(
        httpx.Response(429, headers={"Retry-After": "7"}), json_response({"totalCount": 1})
    )
    client, _ = make_client(handler, clock)
    assert await client.count(SEARCH) == 1
    assert clock.sleeps == [7.0]


async def test_a_429_without_retry_after_waits_out_the_rate_window() -> None:
    """ClinicalTrials.gov sends no Retry-After; its window takes ~7-10 s to let requests in."""
    clock = FakeClock()
    handler = sequence(httpx.Response(429), json_response({"totalCount": 1}))
    client, _ = make_client(handler, clock, throttle_wait=10.0)
    assert await client.count(SEARCH) == 1
    assert clock.sleeps == [10.0]


async def test_retries_timeouts_and_connection_errors() -> None:
    clock = FakeClock()
    handler = sequence(
        httpx.ReadTimeout("slow"), httpx.ConnectError("down"), json_response({"totalCount": 2})
    )
    client, _ = make_client(handler, clock)
    assert await client.count(SEARCH) == 2


async def test_gives_up_after_four_attempts() -> None:
    clock = FakeClock()
    client, transport = make_client(sequence(*[httpx.Response(500)] * 4), clock)
    with pytest.raises(CtgovUnavailable):
        await client.count(SEARCH)
    assert len(transport.requests) == 4
    assert clock.sleeps == [1.0, 2.0, 4.0]


async def test_backoff_is_capped() -> None:
    clock = FakeClock()
    client, _ = make_client(
        sequence(*[httpx.Response(500)] * 8), clock, max_attempts=8, backoff_cap=30.0
    )
    with pytest.raises(CtgovUnavailable):
        await client.count(SEARCH)
    assert max(clock.sleeps) == 30.0


@pytest.mark.parametrize("status", [400, 404])
async def test_client_errors_are_not_retried(status: int) -> None:
    clock = FakeClock()
    handler = sequence(httpx.Response(status, text="Unknown area name: Phse"))
    client, transport = make_client(handler, clock)
    with pytest.raises(CtgovBadRequest, match="Unknown area name"):
        await client.count(SEARCH)
    assert len(transport.requests) == 1


# ---------- circuit breaker ----------


async def test_circuit_opens_after_consecutive_failures_and_recovers() -> None:
    clock = FakeClock()
    responses = [httpx.Response(500)] * 5 + [json_response({"totalCount": 9})]
    client, transport = make_client(
        sequence(*responses), clock, max_attempts=1, breaker_threshold=5, breaker_cooldown=30.0
    )
    for _ in range(5):
        with pytest.raises(CtgovUnavailable):
            await client.count(SEARCH)

    with pytest.raises(CircuitOpen):
        await client.count(SEARCH)
    assert len(transport.requests) == 5  # failed fast, no request sent

    clock.now += 30.0
    assert await client.count(SEARCH) == 9


async def test_success_resets_the_failure_count() -> None:
    clock = FakeClock()
    responses = [httpx.Response(500)] * 4 + [json_response({"totalCount": 1})]
    responses += [httpx.Response(500)] * 4 + [json_response({"totalCount": 1})]
    client, _ = make_client(sequence(*responses), clock, max_attempts=1, breaker_threshold=5)
    for _ in range(2):
        for _ in range(4):
            with pytest.raises(CtgovUnavailable):
                await client.count(SEARCH)
        assert await client.count(SEARCH) == 1


# ---------- paging ----------


def page(ids: list[str], token: str | None = None, total: int | None = None) -> httpx.Response:
    body: dict[str, Any] = {
        "studies": [{"protocolSection": {"identificationModule": {"nctId": i}}} for i in ids]
    }
    if token:
        body["nextPageToken"] = token
    if total is not None:
        body["totalCount"] = total
    return json_response(body)


async def test_fetch_all_follows_page_tokens_including_empty_pages() -> None:
    clock = FakeClock()
    handler = sequence(
        page(["NCT1", "NCT2"], token="t1", total=3), page([], token="t2"), page(["NCT3"])
    )
    client, transport = make_client(handler, clock)
    result = await client.fetch_all(SEARCH, fields=["NCTId", "Phase"])

    assert [s["protocolSection"]["identificationModule"]["nctId"] for s in result.studies] == [
        "NCT1",
        "NCT2",
        "NCT3",
    ]
    assert result.total_count == 3
    first, second, third = (r.url.params for r in transport.requests)
    assert (first["countTotal"], first["pageSize"], first["fields"]) == (
        "true",
        "1000",
        "NCTId,Phase",
    )
    assert "pageToken" not in first
    assert (second["pageToken"], third["pageToken"]) == ("t1", "t2")
    assert second["query.cond"] == third["query.cond"] == '"melanoma"'


async def test_fetch_all_detects_a_changed_result_set() -> None:
    clock = FakeClock()
    client, _ = make_client(sequence(page(["NCT1"], total=2)), clock)
    with pytest.raises(InconsistentResults):
        await client.fetch_all(SEARCH, fields=["NCTId"])


async def test_fetch_all_removes_duplicate_trials() -> None:
    clock = FakeClock()
    client, _ = make_client(
        sequence(page(["NCT1", "NCT2"], token="t", total=2), page(["NCT2"])), clock
    )
    result = await client.fetch_all(SEARCH, fields=["NCTId"])
    assert len(result.studies) == 2


# ---------- data version ----------


async def test_version_is_cached() -> None:
    clock = FakeClock()
    body = {"apiVersion": "2.0.5", "dataTimestamp": "2026-10-23T09:00:04"}
    client, transport = make_client(
        sequence(
            json_response(body), json_response(body | {"dataTimestamp": "2026-10-24T09:00:01"})
        ),
        clock,
        version_ttl=600.0,
    )
    assert (await client.version()).data_timestamp == "2026-10-23T09:00:04"
    clock.now += 599
    await client.version()
    assert len(transport.requests) == 1
    clock.now += 2
    assert (await client.version()).data_timestamp == "2026-10-24T09:00:01"
    assert transport.requests[1].url.path == "/api/v2/version"
