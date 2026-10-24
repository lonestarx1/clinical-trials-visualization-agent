# Design Q17: Error handling

Status: **Decided** (2026-10-24)

## Rule 1: outcomes that aren't charts are not errors

These are valid answers, returned as **200** with `status` set and `visualization: null`. `meta` explains why:

| `status` | When | `meta` contains |
|---|---|---|
| `out_of_scope` | The question is about something we don't support (Q1) | The reason |
| `no_matching_trials` | Valid filters matched 0 trials (Q5 layer 3) | `details.search_counts`: the count of each search (one per comparison group), e.g. `[{"group": null, "count": 0}]`. Per-search, not per-filter ([Q12 revision](12-io-schema.md#revision-2026-10-25-network-encoding-and-no_matching_trials-details-as-built)) |
| `could_not_interpret` | No valid plan within the agent's limits (Q2, D2.4), including a forced `chart_type` that can't show the question ([Q3 revision](03-ai-vs-code.md#optional-request-override)) | The best attempt + the validation errors |

## Rule 2: real errors share one body

```json
{ "error": { "code": "upstream_unavailable", "message": "ClinicalTrials.gov is not responding. Please retry later.",
             "details": { "...": "safe, structured details" }, "trace_id": "uuid" } }
```

Error bodies **never** contain stack traces, prompts, model outputs, keys, or internal config. The `trace_id` links to the full trace (Q16).

| HTTP | `code` | When |
|---|---|---|
| 422 | `invalid_request` | Request validation failed (Q5 layer 1). `details` lists per-field errors (`loc`, `msg`). FastAPI's default 422 body is converted to this format, and so are its routing and auth errors (401, 404, 405: the code is the status name in snake_case). |
| 400 | `rejected_by_policy` | The input guard classified the request as malicious (Q5b). Generic message; the reason is logged only. |
| 401 | `unauthorized` | `GET /v1/usage` without the admin token |
| 404 | `not_found` | Unknown `job_id` / `result_id` / data point, or a path that doesn't exist |
| 405 | `method_not_allowed` | A known path with the wrong HTTP method (the `Allow` header lists the right one) |
| 410 | `expired` | Result or job past retention / no longer valid (Q14). A finished job expires 24 h after finishing, or with its result |
| 429 | `too_many_requests` | **Our own** per-client rate limit; includes a `Retry-After` header |
| 503 | `upstream_unavailable` | ClinicalTrials.gov still failing after retries, or the circuit breaker is open (Q8) |
| 503 | `llm_unavailable` | OpenAI failing after retries **and** the fallback model (Q8) |
| 503 | `safety_check_unavailable` | The guard failed after its retry: fail closed (Q5b) |
| 503 | `budget_exceeded` | The daily LLM spending cap was reached (Q16 `llm_usage`) and the request needs a model call. Cached results are still served: an exact repeat whose plan and result are stored is answered with no model call (Q16). |
| 500 | `internal_error` | Our bug: e.g. ClinicalTrials.gov returned 400 for a query **we** compiled, the citation exactness check failed (Q14), or a response failed schema validation |

## Rule 3: no silent partial answers

If **any** search behind a chart fails after retries (e.g. one group of an "A vs B" comparison, or one parallel slice), the **whole request fails** with the matching error. We never return a chart with a group or slice silently missing. Slices are also cross-checked (sum of slice totals == unsliced total, Q6).

## Rule 4: graceful fallback only where it's safe

| Situation | Behaviour |
|---|---|
| Narration fails its checks after 1 retry | Template title from the fact sheet (the summary was removed 2026-10-24); `meta.narration.fallback = true` (Q4b) |
| Only the chart type is incompatible at the gate | Default chart type for the intent; noted in `meta` (Q3) |
| Sync request exceeds its time budget | Converted to a **background job** (202 + `job_id`), not a 504 timeout (Q6) |
| Guard unavailable | **No** fallback: fail closed (503) |
| Data errors in individual trials (impossible dates, missing fields) | Excluded and counted in `meta.excluded` (Q10), not an error |

## Rule 5: background jobs use the same error body

A failed job is `GET /v1/jobs/{id}` -> `{ "status": "failed", "error": { ...same body... } }`. Jobs that crashed are retried up to `max_attempts` before being marked failed (Q16).

## Logging

Every error is logged with its `trace_id`, error code, stage, and upstream status (if any). 5xx errors are logged at error level, 4xx at info level. Error rates per code are available from `traces` (`outcome`, `http_status`).

## Requirement links

P1-6 (reliable rendering: predictable shapes), P7-8 (correctness and robustness), P7-12 (unambiguous schemas), P3-12 (documented response schema, including errors).
