# Design Q8: Cache, rate limiting, retries

Status: **Decided** (2026-10-24)

## Cache

| # | Decision |
|---|---|
| D8.1 | **Storage: Postgres only** (the same database as background jobs). |
| D8.2 | **Three layers.** Rows store the `dataTimestamp` they were last verified against (not part of the key; see "Revalidate, don't invalidate" below): |

| Layer | Key | Value | Why |
|---|---|---|---|
| L1 API responses | endpoint + normalised params | raw response (page / count / stats) + total count + verified `dataTimestamp` | Cuts API calls and rate-limit pressure; makes example runs reproducible |
| L2 Plans | normalised request (query text + fields) + model/prompt version | validated QueryPlan + planner trace | Same question -> same plan -> consistent answers; saves LLM calls |
| L3 Final responses | plan hash + code/schema version | full visualization response + list of underlying searches + verified `dataTimestamp` | Instant answer for repeat questions |

- **Data version tracking:** `dataTimestamp` is read from `/version` and re-checked about every 10 minutes (configurable). Every cache row records the `dataTimestamp` it was **last verified** against.

### Revalidate, don't invalidate (revised design)

The first draft invalidated **everything** when `dataTimestamp` changed. That is wasteful: each daily refresh touches only a few thousand of ~608k trials. Instead, cached search results are **revalidated** lazily, on next use:

For a cached search `Q` verified at data version `T_old`, when the current version is `T_new`:

1. **Changed-and-matching check:** `countTotal` of `Q AND AREA[LastUpdatePostDate]RANGE[<date of T_old>, MAX]` must be **0**.
2. **Size check:** `countTotal` of `Q` must equal the cached total.

If both pass, the cached result is **exactly** still valid. It's re-stamped with `T_new` (cost: 2 count calls, ~0.7 s, instead of refetching up to 17+ pages). If either fails, it's refetched.

**Why this is exact:**
- A trial that wasn't updated keeps the same record, so it can't enter or leave `Q`'s result set.
- New and edited trials have a recent `LastUpdatePostDate`. If they match `Q`, check 1 catches them.
- Edited trials that **left** `Q`, and removed trials, change the total, so check 2 catches them unless an entering trial exactly compensates, and that trial is caught by check 1.
- The lower bound of the range is inclusive of the old version's date, as a safety margin.

**Per layer:**

| Layer | On data update |
|---|---|
| L1 API responses (pages, counts) | Revalidated lazily, per search, as above |
| L2 Plans | **Never** invalidated by data updates. Plans depend on the question, fields, model and prompt version only. (`count_trials` results used during planning are L1 entries.) |
| L3 Final responses, stored results + citations, finished jobs | Valid while **all** their underlying searches revalidate; otherwise recomputed |

**Caveats still to verify live (open item O5):**
- Does every visible change bump `LastUpdatePostDate`? Registry-side re-indexing (e.g. MeSH re-mapping, synonym dictionary updates) might change search membership or derived fields without it.
- Until that's verified, a **safety ceiling** applies: any entry older than N days (default 7, configurable) is refetched regardless.

Old rows past the ceiling or unused for a while are deleted by a periodic cleanup job.
- **Request coalescing ("single-flight"):** concurrent identical L1 fetches share one in-flight API call.
- **Version fields** (model/prompt version in L2, code/schema version in L3) make deployments invalidate old plans and responses safely.

**As built:** L2 (plans) and L3 (stored results) are implemented, with revalidation as above and the 7-day safety ceiling. Each stored result keeps its searches and totals for revalidation. The L1 page cache and request coalescing are not built ([Q16 implementation status](16-database.md#implementation-status-2026-10-24)).

### Why Postgres, not Redis (recorded alternative)

We considered Redis (an in-memory cache with native TTL, LRU eviction and sub-millisecond reads) and **chose Postgres for now**:

- **The cache is not the bottleneck.** A Postgres lookup takes a few milliseconds. LLM calls (seconds) and ClinicalTrials.gov network calls (0.3-2 s per page) dominate request time, so Redis would barely change it.
- **One fewer service** to deploy and operate. Postgres is already required for background jobs.
- **Durable across restarts**, so a warm cache survives deploys.

**When Redis becomes worth it:** a production service with many users asking frequent questions. There, high cache read rates, in-memory speed, built-in eviction and a shared rate limiter across many app instances would justify an in-memory cache such as Redis. The cache sits behind an interface, so swapping it is a contained change.

## Rate limiting (ClinicalTrials.gov)

| # | Decision |
|---|---|
| D8.3 | **One global limiter** for all requests and background jobs: default **40 requests/min** (20% under the most conservative third-party estimate of ~50/min; see live-probe §8). Configurable. |
| D8.4 | **Concurrency cap**, default **2** in-flight API calls (Q6). Configurable. |
| D8.5 | Single-process deployment for now: the limiter is in-process. With several instances it must move to shared storage (Postgres advisory locks / a token table, or Redis). Documented as a scaling limitation. |

## Retries and failure handling

| # | Applies to | Decision |
|---|---|---|
| D8.6 | ClinicalTrials.gov | **Retry** on 429, 5xx, timeouts and connection errors: up to **4 attempts**, exponential backoff with full jitter (base 1 s, cap 30 s), honouring `Retry-After` if present. |
| D8.7 | ClinicalTrials.gov | **Never retry** 400/404 (our bug or a genuine "not found"); surface them as structured errors. |
| D8.8 | ClinicalTrials.gov | **Circuit breaker:** after N consecutive failures (e.g. 5), fail fast for ~30 s instead of adding load, and return a 503 `upstream_unavailable` (or keep a background job pending and retry later). |
| D8.9 | All HTTP | **Timeouts:** connect 5 s, read 30 s; plus an overall per-request deadline (sync requests) after which the work moves to / stays in a background job. |
| D8.10 | OpenAI | Same retry policy for 429/5xx/timeouts, plus a **fallback model** (e.g. primary `gpt-5.4-mini`, fallback `gpt-4.1-mini`). Every attempt and fallback is recorded in the trace. |

## Requirement links

P7-3 (real-world API handling), P7-8 (robustness), P2-1 (live authoritative source), P6-6 (reproducible example runs).
