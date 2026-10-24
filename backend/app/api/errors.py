"""One error body for every real error (design Q17). Never leaks internals."""

import logging
import uuid
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agents.guard import SafetyCheckUnavailable
from app.ctgov.client import CtgovBadRequest, CtgovUnavailable, InconsistentResults
from app.llm.client import LLMUnavailable
from app.pipeline.citations import CitationMismatch
from app.pipeline.query import BudgetExceeded, RejectedByPolicy, TooManyJobs
from app.store.results import Expired, NotFound

log = logging.getLogger(__name__)


# Exception -> (HTTP status, code, public message). Never includes internal details.
_PUBLIC: list[tuple[type[Exception], int, str, str]] = [
    (RequestValidationError, 422, "invalid_request", "The request is not valid."),
    (RejectedByPolicy, 400, "rejected_by_policy", "Request rejected by input policy."),
    (NotFound, 404, "not_found", "Not found."),
    (Expired, 410, "expired", "This result has expired; please run the query again."),
    (TooManyJobs, 429, "too_many_requests", "Too many background jobs for this client."),
    (
        CtgovUnavailable,
        503,
        "upstream_unavailable",
        "ClinicalTrials.gov is not responding. Please retry later.",
    ),
    (
        InconsistentResults,
        503,
        "upstream_unavailable",
        "ClinicalTrials.gov data changed while reading it. Please retry.",
    ),
    (LLMUnavailable, 503, "llm_unavailable", "The AI service is not responding. Please retry."),
    (
        SafetyCheckUnavailable,
        503,
        "safety_check_unavailable",
        "Safety check unavailable, please retry later.",
    ),
    (
        BudgetExceeded,
        503,
        "budget_exceeded",
        "Today's AI budget is used up; cached answers are still available.",
    ),
]


def classify(exc: Exception) -> tuple[int, str, str]:
    for kind, status, code, message in _PUBLIC:
        if isinstance(exc, kind):
            return status, code, message
    return 500, "internal_error", "Something went wrong on our side."


def error_body(exc: Exception, trace_id: str) -> dict[str, Any]:
    _, code, message = classify(exc)
    return {"code": code, "message": message, "details": None, "trace_id": trace_id}


def error_response(
    status: int,
    code: str,
    message: str,
    details: Any = None,
    trace_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    trace_id = trace_id or str(uuid.uuid4())
    body = {"error": {"code": code, "message": message, "details": details, "trace_id": trace_id}}
    return JSONResponse(status_code=status, content=body, headers=headers)


async def _invalid(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [{"loc": [str(p) for p in err["loc"]], "msg": err["msg"]} for err in exc.errors()]
    return error_response(422, "invalid_request", "The request is not valid.", details)


_HTTP_MESSAGES = {
    401: "Authentication required.",
    404: "Not found.",
    405: "Method not allowed.",
}


async def _http(request: Request, exc: Exception) -> JSONResponse:
    """Routing and auth errors (unknown path 404, wrong method 405, 401): the same body.

    The code is the status phrase in snake_case (`not_found`, `method_not_allowed`,
    `unauthorized`); the framework's own detail ("Not Found") is replaced by a sentence.
    """
    assert isinstance(exc, StarletteHTTPException)
    status = HTTPStatus(exc.status_code)
    code = status.phrase.lower().replace(" ", "_").replace("-", "_")
    message = _HTTP_MESSAGES.get(exc.status_code, f"{status.phrase}.")
    headers = dict(exc.headers) if exc.headers else None
    return error_response(exc.status_code, code, message, headers=headers)


async def _upstream(request: Request, exc: Exception) -> JSONResponse:
    response = error_response(
        503, "upstream_unavailable", "ClinicalTrials.gov is not responding. Please retry later."
    )
    log.error("upstream failure: %s", exc)
    return response


async def _rejected(request: Request, exc: Exception) -> JSONResponse:
    return error_response(400, "rejected_by_policy", "Request rejected by input policy.")


async def _safety_unavailable(request: Request, exc: Exception) -> JSONResponse:
    return error_response(
        503, "safety_check_unavailable", "Safety check unavailable, please retry later."
    )


async def _llm_unavailable(request: Request, exc: Exception) -> JSONResponse:
    log.error("llm failure: %s", exc)
    return error_response(503, "llm_unavailable", "The AI service is not responding. Please retry.")


async def _internal(request: Request, exc: Exception) -> JSONResponse:
    response = error_response(500, "internal_error", "Something went wrong on our side.")
    log.exception("internal error on %s", request.url.path, exc_info=exc)
    return response


async def _known(request: Request, exc: Exception) -> JSONResponse:
    status, code, message = classify(exc)
    if status >= 500:
        log.error("%s: %s", code, exc)
    return error_response(status, code, message)


def install_error_handlers(app: FastAPI) -> None:
    for kind in (NotFound, Expired, TooManyJobs, BudgetExceeded):
        app.add_exception_handler(kind, _known)
    app.add_exception_handler(RequestValidationError, _invalid)
    app.add_exception_handler(StarletteHTTPException, _http)
    app.add_exception_handler(CtgovUnavailable, _upstream)
    app.add_exception_handler(InconsistentResults, _upstream)
    app.add_exception_handler(RejectedByPolicy, _rejected)
    app.add_exception_handler(SafetyCheckUnavailable, _safety_unavailable)
    app.add_exception_handler(LLMUnavailable, _llm_unavailable)
    # A 400 from the API for a query we compiled, or a citation mismatch, is our bug.
    app.add_exception_handler(CtgovBadRequest, _internal)
    app.add_exception_handler(CitationMismatch, _internal)
    app.add_exception_handler(Exception, _internal)
