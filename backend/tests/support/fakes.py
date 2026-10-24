"""Deterministic stand-ins for time and the network."""

import json
from collections.abc import Callable
from typing import Any

import httpx


class FakeClock:
    """Time only moves when someone sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += max(seconds, 0)


Handler = Callable[[httpx.Request], httpx.Response]


class RecordingTransport(httpx.MockTransport):
    """Serves responses from a handler and records every request."""

    def __init__(self, handler: Handler) -> None:
        self.requests: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        super().__init__(record)


def json_response(body: Any, status: int = 200, **headers: str) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(body), headers=headers)


def sequence(*responses: httpx.Response | Exception) -> Handler:
    """Return the given responses (or raise the given errors) in order."""
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return handler
