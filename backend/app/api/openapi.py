"""OpenAPI metadata: the API reference that /docs (Swagger) and /redoc render (design Q12).

Documentation only: nothing here changes how a request is handled.
"""

import copy
from typing import Any

from fastapi import FastAPI

from app.agents.guard import SafetyCheckUnavailable
from app.api import examples
from app.api.errors import classify, http_error
from app.ctgov.client import CtgovUnavailable, InconsistentResults
from app.llm.client import LLMUnavailable
from app.pipeline.query import BudgetExceeded, RejectedByPolicy, TooManyJobs
from app.schemas.endpoints import (
    CitationPage,
    ErrorResponse,
    JobAccepted,
    JobStatus,
    Options,
    UsageSummary,
)
from app.store.jobs import JobExpired
from app.store.results import Expired, NotFound

DESCRIPTION = """
Turns a natural-language question about [ClinicalTrials.gov](https://clinicaltrials.gov)
into a chart specification in Vega-Lite style. Every data point cites the trials behind it,
and `meta` says how the question was read, which filters were applied, how trials were
counted and which ClinicalTrials.gov API queries produced the numbers.

## Flow

1. **Ask:** `POST /v1/query` with a `query` and, optionally, structured fields
   (`drug_name`, `condition`, `trial_phase`, `compare`, `chart_type`...). Fields are
   authoritative: they override what the AI reads in the question, and a conflict is
   reported in `meta.warnings`.
2. **200:** most questions are answered synchronously. `status` is `ok` (the chart is in
   `visualization`), or `no_matching_trials`, `out_of_scope` or `could_not_interpret`
   (`visualization` is `null` and `meta.details` explains why). These are answers, not errors.
3. **202:** a broad question whose retrieval is estimated to take longer than about a minute
   runs as a background job instead. The body has a `job_id` and a `poll_url`.
4. **Poll:** `GET /v1/jobs/{job_id}` every few seconds until `status` is `succeeded`
   (the normal response is in `result`) or `failed` (the error body is in `error`).
   `progress` reports the ClinicalTrials.gov pages fetched so far.
5. **Cite:** each data point has a stable `key`, its full `citation_count` and up to
   `citations_per_datum` citations inline (`citations: "full"` inlines all of them, up to
   2,000 per response). Page through every trial behind one data point
   with `GET /v1/results/{result_id}/citations?datum=<key>`. Stored results expire after
   24 hours (then `410 expired`).

`GET /v1/options` lists the dimensions, measures, chart types and filter values (with
labels), so a client can build pickers. `GET /health` reports the database and
ClinicalTrials.gov status.

## Errors

Real errors share one body, and never contain internal details:

```json
{"error": {"code": "upstream_unavailable", "message": "...", "details": null, "trace_id": "..."}}
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `rejected_by_policy` | The input guard classified the request as malicious |
| 401 | `unauthorized` | `GET /v1/usage` without the admin token |
| 404 | `not_found` | Unknown job, result, data point or path |
| 405 | `method_not_allowed` | Wrong HTTP method for the path (see the `Allow` header) |
| 410 | `expired` | The stored result, or the finished job, is past its 24-hour retention |
| 422 | `invalid_request` | Validation failed; `details` lists each field (`loc`, `msg`) |
| 429 | `too_many_requests` | Rate limit (with `Retry-After`), or too many active background jobs |
| 500 | `internal_error` | A bug on our side |
| 503 | `budget_exceeded` | Today's AI budget is used up |
| 503 | `upstream_unavailable` | ClinicalTrials.gov is failing or changed data mid-read; retry |
| 503 | `llm_unavailable` | The AI model and its fallback are failing; retry |
| 503 | `safety_check_unavailable` | The input guard is failing; the API fails closed; retry |

Quote the `trace_id` when reporting a problem.

## Limits

- **Rate limit:** 300 requests per minute per client IP on `/v1/*` (setting
  `RATE_LIMIT_PER_IP_PER_MIN`). Over it, `429 too_many_requests` with a `Retry-After`
  header in seconds. `/health` and the docs are not limited.
- **Background jobs:** at most 10 pending or running jobs per client IP
  (`MAX_ACTIVE_JOBS_PER_IP`); another broad question gets `429 too_many_requests`.
  Asking the same question again while its job is active returns the same job.
- **Daily AI budget:** every guard, planner and narrator call is costed. Once today's spend
  (UTC day) reaches the cap (USD 100 by default, `LLM_DAILY_BUDGET_USD`), a question that
  needs a model call gets `503 budget_exceeded` until midnight UTC. An exact repeat of a
  question whose stored answer is still valid is still answered, with no model call (not
  even the guard: it passed the first time). Jobs, citations and options keep working.
  `meta.usage` reports each answer's calls and cost.
- **ClinicalTrials.gov:** the API calls it at most about 40 times per minute for all users
  together, which is why broad questions run as background jobs.

## Versions

`info.version` is the code version. Every response carries `schema_version` (now `2.0`),
which changes when the response shape changes in a way that can break a client.

No authentication is needed, except for `GET /v1/usage` (admin bearer token).
"""

SERVERS: list[dict[str, Any]] = [
    {"url": "https://api.cheiron.engineeradriel.com", "description": "Production"},
    {"url": "http://localhost:8000", "description": "Local (make up)"},
]

TAGS: list[dict[str, Any]] = [
    {
        "name": "query",
        "description": "Ask a question: get a chart specification with citations, "
        "or a background job for a broad question.",
    },
    {
        "name": "jobs",
        "description": "Poll the background job started by a broad question (202).",
    },
    {
        "name": "citations",
        "description": "Every trial behind one data point of a stored result, "
        'paginated. Inline citations are a sample unless `citations: "full"` was asked.',
    },
    {
        "name": "options",
        "description": "The registry: dimensions, measures, chart types and filter values "
        "with labels, for building pickers.",
    },
    {"name": "health", "description": "Liveness and readiness, used by the container probes."},
    {"name": "admin", "description": "Operator endpoints. Need the admin bearer token."},
    {
        "name": "debug",
        "description": "Run a hand-written QueryPlan without the AI stages. "
        "Disabled in production (`ENABLE_DEBUG_ENDPOINTS=false`).",
    },
]


# ---------- documented responses ----------

ERROR_TRACE_ID = "5b3f9a1e-2c4d-4e8f-9a7b-1c2d3e4f5a6b"
RATE_LIMIT_MESSAGE = "Too many requests; slow down."  # app/api/ratelimit.py


def _error(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "error": {"code": code, "message": message, "details": details, "trace_id": ERROR_TRACE_ID}
    }


def _public(exc: Exception) -> dict[str, Any]:
    """The body the error handlers return for this exception: same code and message."""
    _, code, message = classify(exc)
    return _error(code, message)


def _invalid(*fields: tuple[list[str], str]) -> dict[str, Any]:
    details = [{"loc": loc, "msg": msg} for loc, msg in fields]
    return _error("invalid_request", "The request is not valid.", details)


def ok(description: str, **named: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    """A documented status with named (summary, body) examples."""
    return {
        "description": description,
        "content": {
            "application/json": {
                "examples": {
                    name: {"summary": summary, "value": body}
                    for name, (summary, body) in named.items()
                }
            }
        },
    }


def errors(description: str, **named: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    """An error status: the shared error body, with named (summary, body) examples."""
    return ok(description, **named) | {"model": ErrorResponse}


RETRY_AFTER = {
    "Retry-After": {
        "description": "Seconds until the client may retry (rate limit only).",
        "schema": {"type": "integer"},
    }
}
RATE_LIMIT = ("Rate limit", _error("too_many_requests", RATE_LIMIT_MESSAGE))
RATE_LIMITED = errors(
    "More than `RATE_LIMIT_PER_IP_PER_MIN` (300) requests in a minute from this client on "
    "`/v1/*` (`too_many_requests`). Wait `Retry-After` seconds.",
    too_many_requests=RATE_LIMIT,
) | {"headers": RETRY_AFTER}
INTERNAL = errors(
    "A bug on our side (`internal_error`). Quote the `trace_id`.",
    internal_error=("Internal error", _public(Exception())),
)
COMMON: dict[int | str, dict[str, Any]] = {429: RATE_LIMITED, 500: INTERNAL}
NOT_FOUND = _public(NotFound())
UPSTREAM: dict[str, tuple[str, dict[str, Any]]] = {
    "upstream_unavailable": ("ClinicalTrials.gov is failing", _public(CtgovUnavailable())),
    "upstream_changed": (
        "ClinicalTrials.gov data changed while reading it",
        _public(InconsistentResults()),
    ),
}

QUERY_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: ok(
        "An answer. `status` is `ok` with a chart, or `no_matching_trials`, `out_of_scope` or "
        "`could_not_interpret` with `visualization: null` and the reason in `meta.details`.",
        ok=("ok: bar chart (breast cancer trials by phase)", examples.QUERY_OK),
        ok_network=("ok: network graph (drugs in melanoma trials)", examples.QUERY_NETWORK),
        no_matching_trials=(
            "no_matching_trials: a misspelt drug_name matches no trial",
            examples.QUERY_NO_MATCH,
        ),
        out_of_scope=("out_of_scope: with a suggested question", examples.QUERY_OUT_OF_SCOPE),
        could_not_interpret=(
            "could_not_interpret: no valid plan within the planner's steps",
            examples.QUERY_COULD_NOT_INTERPRET,
        ),
    ),
    202: ok(
        "A broad question runs as a background job. Poll `poll_url` (`GET /v1/jobs/{job_id}`).",
        job=("Background job", examples.JOB_ACCEPTED),
    )
    | {"model": JobAccepted},
    400: errors(
        "The input guard classified the request as malicious (`rejected_by_policy`). The "
        "reason is not disclosed.",
        rejected_by_policy=("Rejected by the input guard", _public(RejectedByPolicy())),
    ),
    422: errors(
        "Validation failed (`invalid_request`): `details` has one `{loc, msg}` per invalid "
        "field. Unknown fields are rejected.",
        invalid_request=(
            "Blank question and an unknown field",
            _invalid(
                (["body", "query"], "String should have at least 1 character"),
                (["body", "colour"], "Extra inputs are not permitted"),
            ),
        ),
        bad_compare=(
            "Only one compare group",
            _invalid((["body", "compare"], "Value error, compare needs 2-4 groups")),
        ),
    ),
    429: errors(
        "Rate limit (with `Retry-After`), or this client already has "
        "`MAX_ACTIVE_JOBS_PER_IP` (10) pending or running background jobs "
        "(`too_many_requests`).",
        rate_limit=RATE_LIMIT,
        too_many_jobs=("Too many background jobs", _public(TooManyJobs())),
    )
    | {"headers": RETRY_AFTER},
    500: INTERNAL,
    503: errors(
        "A dependency or the daily budget stops the answer. Retry later; `budget_exceeded` "
        "lasts until midnight UTC, but cached answers are still served meanwhile.",
        budget_exceeded=("Today's AI budget is used up", _public(BudgetExceeded())),
        **UPSTREAM,
        llm_unavailable=("The AI model and its fallback are failing", _public(LLMUnavailable())),
        safety_check_unavailable=(
            "The input guard is failing (the API fails closed)",
            _public(SafetyCheckUnavailable()),
        ),
    ),
}

JOB_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: ok(
        "The job. `result` is set once `succeeded`, `error` once `failed`.",
        running=("Running", examples.JOB_RUNNING),
        succeeded=("Succeeded: `result` is the normal response", examples.JOB_SUCCEEDED),
        failed=("Failed: `error` is the shared error body", examples.JOB_FAILED),
    )
    | {"model": JobStatus},
    404: errors(
        "No such job, or this deployment has no database (`not_found`).",
        not_found=("Unknown job_id", NOT_FOUND),
    ),
    410: errors(
        "The job finished more than 24 hours ago, or its stored result has expired; ask the "
        "question again (`expired`).",
        expired=("Expired job", _public(JobExpired())),
    ),
    422: errors(
        "`job_id` is not a UUID (`invalid_request`).",
        invalid_request=(
            "Malformed job_id",
            _invalid(
                (
                    ["path", "job_id"],
                    "Input should be a valid UUID, invalid character: found `n` at 0",
                )
            ),
        ),
    ),
    **COMMON,
}

CITATION_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: ok(
        "One page of citations, in the same order as the inline sample.",
        first_page=("First page with page_size=1", examples.CITATION_PAGE),
    )
    | {"model": CitationPage},
    404: errors(
        "No such result, no data point with that `key` in it, or no database (`not_found`).",
        not_found=("Unknown result_id or datum", NOT_FOUND),
    ),
    410: errors(
        "The stored result is past its 24-hour retention; ask the question again (`expired`).",
        expired=("Expired result", _public(Expired())),
    ),
    422: errors(
        "Malformed `result_id`, missing `datum`, or `cursor` / `page_size` out of range "
        "(`invalid_request`).",
        invalid_request=("Missing datum", _invalid((["query", "datum"], "Field required"))),
    ),
    **COMMON,
}

OPTIONS_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: ok("The registry (shortened in this example).", options=("Options", examples.OPTIONS))
    | {"model": Options},
    **COMMON,
}

USAGE_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: ok("Today's usage and the budget.", usage=("Usage", examples.USAGE))
    | {"model": UsageSummary},
    401: errors(
        "Missing or wrong admin token, or no `ADMIN_TOKEN` configured (`unauthorized`).",
        unauthorized=("No or wrong token", _error(*http_error(401))),
    ),
    404: errors(
        "This deployment has no database (`not_found`).",
        not_found=("No database", NOT_FOUND),
    ),
    422: errors(
        "Invalid request (`invalid_request`); the shared body, should a header ever fail "
        "validation.",
        invalid_request=(
            "Invalid header",
            _invalid((["header", "authorization"], "Input should be a valid string")),
        ),
    ),
    **COMMON,
}

HEALTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: ok(
        "The database is reachable. A ClinicalTrials.gov outage shows in `checks` but keeps "
        "`status` at `ok`.",
        ok=("Healthy", examples.HEALTH_OK),
        ctgov_down=("ClinicalTrials.gov unreachable", examples.HEALTH_CTGOV_DOWN),
    ),
    503: ok(
        "The database is unreachable.",
        unavailable=("Database down", examples.HEALTH_UNAVAILABLE),
    ),
}

DEBUG_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: ok("The answer, as for `POST /v1/query`.", ok=("ok: bar chart", examples.DEBUG_OK)),
    422: errors(
        "The plan or the options are invalid (`invalid_request`).",
        invalid_request=(
            "Unknown dimension",
            _invalid((["body", "plan", "dimension"], "Value error, unknown dimension 'colour'")),
        ),
    ),
    503: errors("ClinicalTrials.gov is failing (`upstream_unavailable`).", **UPSTREAM),
    **COMMON,
}


def install_openapi(app: FastAPI) -> None:
    """Keep the nulls in the documented example bodies.

    FastAPI drops every null from the generated document, which would remove meaningful
    values such as `visualization: null` or `result_id: null` from the examples. After
    generation, this puts the declared example bodies back as written.
    """
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        schema = generate()  # cached by FastAPI; restoring is idempotent
        for (path, method), responses in DOCUMENTED.items():
            operation = schema["paths"].get(path, {}).get(method)
            if operation is None:  # e.g. the debug route when disabled
                continue
            for status, declared in responses.items():
                content = declared.get("content", {}).get("application/json", {})
                if "examples" in content:
                    documented = operation["responses"][str(status)]["content"]
                    documented["application/json"]["examples"] = copy.deepcopy(content["examples"])
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


DOCUMENTED: dict[tuple[str, str], dict[int | str, dict[str, Any]]] = {
    ("/v1/query", "post"): QUERY_RESPONSES,
    ("/v1/jobs/{job_id}", "get"): JOB_RESPONSES,
    ("/v1/results/{result_id}/citations", "get"): CITATION_RESPONSES,
    ("/v1/options", "get"): OPTIONS_RESPONSES,
    ("/v1/usage", "get"): USAGE_RESPONSES,
    ("/v1/debug/plan", "post"): DEBUG_RESPONSES,
    ("/health", "get"): HEALTH_RESPONSES,
}
