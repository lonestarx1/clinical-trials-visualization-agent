"""One error body for every real error (design Q17). Never leaks internals."""

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.ctgov.client import CtgovBadRequest, CtgovUnavailable, InconsistentResults
from app.pipeline.citations import CitationMismatch

log = logging.getLogger(__name__)


def error_response(
    status: int, code: str, message: str, details: Any = None, trace_id: str | None = None
) -> JSONResponse:
    trace_id = trace_id or str(uuid.uuid4())
    body = {"error": {"code": code, "message": message, "details": details, "trace_id": trace_id}}
    return JSONResponse(status_code=status, content=body)


async def _invalid(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [{"loc": [str(p) for p in err["loc"]], "msg": err["msg"]} for err in exc.errors()]
    return error_response(422, "invalid_request", "The request is not valid.", details)


async def _upstream(request: Request, exc: Exception) -> JSONResponse:
    response = error_response(
        503, "upstream_unavailable", "ClinicalTrials.gov is not responding. Please retry later."
    )
    log.error("upstream failure: %s", exc)
    return response


async def _internal(request: Request, exc: Exception) -> JSONResponse:
    response = error_response(500, "internal_error", "Something went wrong on our side.")
    log.exception("internal error on %s", request.url.path, exc_info=exc)
    return response


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _invalid)
    app.add_exception_handler(CtgovUnavailable, _upstream)
    app.add_exception_handler(InconsistentResults, _upstream)
    # A 400 from the API for a query we compiled, or a citation mismatch, is our bug.
    app.add_exception_handler(CtgovBadRequest, _internal)
    app.add_exception_handler(CitationMismatch, _internal)
    app.add_exception_handler(Exception, _internal)
