"""Per-client request limit (design Q19): RATE_LIMIT_PER_IP_PER_MIN on /v1/*, 429 + Retry-After.

In memory: correct for one instance; several instances would need a shared store (Redis).
"""

import math
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.api.deps import client_ip
from app.api.errors import error_response

WINDOW = 60.0


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, per_minute: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.per_minute = per_minute
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)
        now, hits = time.monotonic(), self.hits[client_ip(request)]
        while hits and now - hits[0] > WINDOW:
            hits.popleft()
        if len(hits) >= self.per_minute:
            response = error_response(429, "too_many_requests", "Too many requests; slow down.")
            response.headers["Retry-After"] = str(max(1, math.ceil(WINDOW - (now - hits[0]))))
            return response
        hits.append(now)
        return await call_next(request)
