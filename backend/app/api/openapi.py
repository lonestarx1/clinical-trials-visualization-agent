"""OpenAPI metadata: the API reference that /docs (Swagger) and /redoc render (design Q12).

Documentation only: nothing here changes how a request is handled.
"""

from typing import Any

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
   `citations_per_datum` citations inline. Page through every trial behind one data point
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
| 404 | `not_found` | Unknown job, result or data point |
| 410 | `expired` | The stored result is past its 24-hour retention |
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
  (UTC day) reaches the cap (USD 100 by default, `LLM_DAILY_BUDGET_USD`), `POST /v1/query`
  returns `503 budget_exceeded` until midnight UTC. Stored results stay readable through
  the jobs and citations endpoints. `meta.usage` reports each answer's calls and cost.
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
        "paginated. Inline citations are only a sample.",
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
