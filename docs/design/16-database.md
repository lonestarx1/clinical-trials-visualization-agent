# Design Q16: Database schema (Postgres)

Status: **Decided** (2026-10-24)

Postgres is the only datastore (Q8, Q15). It holds the API response cache, plan cache, results + citations, background jobs, traces, and data versions. The exact DDL is generated from SQLAlchemy models + Alembic migrations during implementation and must match this design.

## Implementation status (2026-10-24)

Built: `data_versions`, `plan_cache`, `results`, `result_datums`, `result_citations`, `jobs`, `llm_usage` (migration `6ebfd3b4b50c`). Not built (cut line 4 in the implementation plan): `api_searches` / `api_pages` (L1 page cache) and `traces`. Consequences: `results.searches` stores each search's params and total count as JSON (used for revalidation) instead of keys into `api_searches`, and `llm_usage.trace_id` has no foreign key.

**Revision (2026-10-25): the mirror's tables.** Migration `b3e1c0a7d222` adds the `registry` schema for the mirror behind `fast` mode ([Q22](22-term-sets.md)): `registry.trials` and `registry.sync_runs` (section 11). They are filled only when `MIRROR_SYNC_ENABLED` is on. Migration `c4f2d1b8e333` adds `registry.term_sets` and `registry.term_members` (section 12).

**Revision (2026-10-25): citation sources.** Migration `d5a3e2c9f444` adds `source`, `next_page_token` and `complete` to `result_datums` (section 6), so the citations endpoint can page a sampled data point's trials from the API on demand ([Q14](14-citations.md)).

## Conventions

| Topic | Rule |
|---|---|
| Timestamps | `timestamptz`, stored in UTC. The API's `dataTimestamp` (`"2026-10-23T09:00:04"`, no zone; UTC per the docs) is stored as `timestamptz` UTC. |
| Hash keys | `char(64)` = SHA-256 hex of a **canonical JSON** form (sorted keys, normalised whitespace, defaults filled in, user terms trimmed and Unicode-normalised). The same logical request always gives the same key. |
| IDs exposed to clients | `uuid` (v4), e.g. `result_id`, `job_id`, `trace_id`. Never guessable sequential integers. |
| Raw API bodies | `bytea`, **gzip-compressed raw bytes** exactly as received. Not JSONB: JSONB re-serialises (key order, number formats), and we want byte-exact source records for citation checks. ~2 MB pages compress to roughly 10-15%. |
| Our own structured data | `jsonb` (plans, responses, traces, evidence) |
| Enums | Postgres `text` + `CHECK` constraint (easier to migrate than native enum types) |
| Deletes | Foreign keys `ON DELETE CASCADE` where a child can't outlive its parent |

## Entity diagram

**Detailed diagram (every column, type, key and link):** [`erd/schema.pdf`](erd/schema.pdf), generated from [`erd/schema.dot`](erd/schema.dot) with Graphviz:
`dot -Tpdf docs/design/erd/schema.dot -o docs/design/erd/schema.pdf`. The `.dot` file is the source of truth; regenerate the PDF after any schema change.

Simplified overview:

```
                    +------------------+
                    |  data_versions   |
                    +------------------+
                      |1            |1
         verified     |             |    verified
         against      |N            |N   against
          +------------------+    +-----------+  1     N  +----------------+  1     N  +--------------------+
          |   api_searches   |    |  results  |-----------|  result_datums |-----------|  result_citations  |
          +------------------+    +-----------+           +----------------+           +--------------------+
                 |1                ^0..1   ^0..1
                 |N                |       |
          +------------------+     |       |
          |    api_pages     |     |       |
          +------------------+     |       |
                         produces  |       |  describes
                           +-------+--+  +-+--------+
                           |   jobs   |  |  traces  |---- describes (0..1) ----> jobs
                           +----------+  +----------+

  traces 1 --- N llm_usage <--- N 1 jobs    (one row per LLM call; each FK optional)
  results.search_keys[] ...> api_searches   (logical reference, no FK)
  plan_cache                                (standalone, no relations)
  registry.trials, registry.sync_runs       (the mirror, Q22; own schema, no FKs to app tables)
  registry.term_sets 1 --- N registry.term_members
```

Not built: `api_searches`, `api_pages` and `traces` (see "Implementation status").

Reading the diagram: `1 -- N` means "one row on this side, many on the other". `0..1` means optional (e.g. a job has a result only after it succeeds).

`results.search_keys` references `api_searches` logically (array, no FK), because a search row may be refreshed or cleaned up independently.

---

## 1. `data_versions`: API data versions we have seen

| Column | Type | Notes |
|---|---|---|
| `data_timestamp` | timestamptz | **PK**. From `/version` |
| `api_version` | text | e.g. `2.0.5` |
| `first_seen_at` | timestamptz | When we first observed this version |
| `last_checked_at` | timestamptz | Last `/version` poll that returned it |

Used by revalidation (Q8): "what is the previous version, and when did it start?"

## 2. `api_searches`: one row per distinct API search (L1 cache, search level)

A "search" = endpoint + canonical params **excluding** paging (`pageToken`, `countTotal`). This is the unit of revalidation.

| Column | Type | Notes |
|---|---|---|
| `search_key` | char(64) | **PK**. Hash of endpoint + canonical params (incl. `fields`, `sort`, and `pageSize` for page searches) |
| `endpoint` | text | `/studies`, `/stats/field/values`, ... |
| `params` | jsonb | Canonical params (for debugging and for reproducing the query) |
| `kind` | text | `CHECK in ('count','pages','stats','study')` |
| `total_count` | integer | `totalCount` from the API (null for stats) |
| `pages_expected` | integer | `ceil(total_count / page_size)` for `pages` |
| `complete` | boolean | All pages fetched successfully |
| `verified_data_ts` | timestamptz | **FK -> data_versions**. Version this result was last verified against |
| `fetched_at` | timestamptz | First full fetch |
| `last_verified_at` | timestamptz | Last successful revalidation |
| `last_used_at` | timestamptz | For cleanup |

Indexes: `(last_used_at)` for cleanup; `(verified_data_ts)`.

## 3. `api_pages`: the raw pages of a search

| Column | Type | Notes |
|---|---|---|
| `search_key` | char(64) | **PK part**, **FK -> api_searches** `ON DELETE CASCADE` |
| `page_index` | integer | **PK part**. 0-based. Keyed by index, **not** by `pageToken` (tokens are opaque and may not survive data updates) |
| `n_studies` | integer | Studies in this page (can be 0: the docs say empty pages are possible) |
| `body_gz` | bytea | gzip of the raw response bytes |
| `raw_bytes` | integer | Uncompressed size (for monitoring) |
| `fetched_at` | timestamptz | |

Count-only and stats searches store their (small) body as page 0.

## 4. `plan_cache`: L2 plan cache

| Column | Type | Notes |
|---|---|---|
| `request_key` | char(64) | **PK**. Hash of normalised query text + canonical fields + `planner_version` |
| `planner_version` | text | Model name + prompt version + registry version. A change = a new key (natural invalidation) |
| `plan` | jsonb | Validated QueryPlan (after the code gate) |
| `planner_trace` | jsonb | Tool calls, attempts, assumptions |
| `created_at` | timestamptz | |
| `last_used_at` | timestamptz | |
| `hit_count` | integer | Default 0 |

Not invalidated by data updates (Q8).

## 5. `results`: final responses (L3 cache + `result_id`)

Rows are **immutable**: a recomputation creates a new row, so a `result_id` a client holds never changes content under it.

| Column | Type | Notes |
|---|---|---|
| `result_id` | uuid | **PK**, returned to clients |
| `result_key` | char(64) | Hash of canonical plan + citation options + `code_version` + `schema_version` (L3 lookup key) |
| `status` | text | `CHECK in ('ok','no_matching_trials','out_of_scope','could_not_interpret')` |
| `request` | jsonb | Original request (sanitised) |
| `plan` | jsonb | Plan used |
| `response` | jsonb | Full response body as returned (with sampled citations) |
| `search_keys` | char(64)[] | Underlying `api_searches` (for revalidation) |
| `verified_data_ts` | timestamptz | **FK -> data_versions** |
| `schema_version` | text | Response schema version |
| `code_version` | text | Git SHA / app version |
| `created_at` | timestamptz | |
| `expires_at` | timestamptz | Retention (default 24 h, configurable) |

Indexes: `(result_key, created_at DESC)` to find the latest result for a plan; `(expires_at)` for cleanup.

## 6. `result_datums`: one row per data point (bar, bucket, bin, point, node, edge, metric)

| Column | Type | Notes |
|---|---|---|
| `result_id` | uuid | **PK part**, **FK -> results** `ON DELETE CASCADE` |
| `datum_key` | text | **PK part**. Stable key within the result, e.g. `bar:Phase 3`, `node:drug:carboplatin`, `edge:drug:carboplatin|drug:paclitaxel`, `bin:0-50` |
| `label` | text | Display label |
| `value` | double precision | The plotted value |
| `citation_count` | integer | All contributing trials |
| `citation_source` | text | `CHECK in ('trials','api_query')`. Count-only strategies (Q6 S1/S2) use `api_query` |
| `source_query` | jsonb | For `api_query`: URL + params + total count |
| `citations_materialized` | boolean | `false` until on-demand citation fetching has filled `result_citations` (count-only datums) |

**As built (2026-10-25):** the last three columns were replaced by three others (migration `d5a3e2c9f444`):

| Column | Type | Notes |
|---|---|---|
| `source` | jsonb | Null for a data point whose every trial is in `result_citations`. For a sampled one (a trials-per-year row counted per year, Q6 S2): the API search that lists all its trials (params, fields, sort, dimension) |
| `next_page_token` | text | The API page token of the next unread page of `source` |
| `complete` | boolean | Default `true`. `false` while `source` still has unread pages; the citations endpoint reads them on demand and appends to `result_citations` |

## 7. `result_citations`: full citation lists (paginated endpoint, Q14)

| Column | Type | Notes |
|---|---|---|
| `result_id` | uuid | **PK part**, FK (with `datum_key`) **-> result_datums** `ON DELETE CASCADE` |
| `datum_key` | text | **PK part** |
| `rank` | integer | **PK part**. Fixed order (latest start date, then NCT ID), 0-based |
| `nct_id` | char(11) | |
| `title` | text | Brief title (context) |
| `evidence` | jsonb | `[{ "field": "protocolSection.designModule.phases", "excerpt": "PHASE3" }, ...]` |

Pagination uses **keyset** on the PK: `WHERE result_id=$1 AND datum_key=$2 AND rank >= $3 ORDER BY rank LIMIT $4`. Stable, index-only, no `OFFSET` scans.

Volume estimate: a broad country chart (~17k trials × ~1.5 countries) is about 25k rows per result, inserted with a bulk `COPY` / multi-row insert.

## 8. `jobs`: background jobs (Q6)

| Column | Type | Notes |
|---|---|---|
| `job_id` | uuid | **PK**, returned to clients |
| `request_key` | char(64) | Same hash as `plan_cache` / request dedupe |
| `request` | jsonb | Sanitised request |
| `plan` | jsonb | Plan (jobs are created after planning) |
| `status` | text | `CHECK in ('pending','running','succeeded','failed','cancelled')` |
| `progress` | jsonb | `{ "stage": "retrieve", "pages_done": 120, "pages_total": 609 }` |
| `estimated_seconds` | integer | Estimate at creation |
| `result_id` | uuid | **FK -> results** (null until succeeded) |
| `error` | jsonb | Same body format as API errors (Q17) |
| `attempts` | integer | Default 0 |
| `max_attempts` | integer | Default 3 |
| `locked_by` | text | Worker ID holding the job |
| `heartbeat_at` | timestamptz | Worker heartbeat while running |
| `trace_id` | uuid | |
| `client_ip` | text | Added in the build: the per-IP active-job limit (`MAX_ACTIVE_JOBS_PER_IP`, Q19) |
| `created_at`, `started_at`, `finished_at` | timestamptz | |
| `expires_at` | timestamptz | Retention after finishing (24 h). Polling a job past it, or a succeeded job whose result has expired, returns **410 `expired`**, like results |

Indexes / constraints:
- **One active job per identical request:** `UNIQUE (request_key) WHERE status IN ('pending','running')` (partial unique index). A duplicate request returns the existing `job_id`.
- **Worker pickup:** index `(status, created_at)`. Claim with
  `SELECT ... WHERE status='pending' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1`, then `UPDATE ... SET status='running', locked_by=..., started_at=now()`.
- **Valid transitions** are enforced by conditional updates (`UPDATE ... WHERE job_id=$1 AND status='running'`): `pending -> running -> succeeded | failed`, `pending -> cancelled`, `running -> pending` (crash recovery only).
- **Revision (2026-10-25): cancellation.** `running -> cancelled` is also valid. `DELETE /v1/jobs/{job_id}` locks the row (`SELECT ... FOR UPDATE`) and, if it is `pending` or `running`, sets `status='cancelled'`, `error` (`code: cancelled`), `finished_at` and `expires_at`. The worker's writes (`progress`, `succeed`, `fail`) are conditional on `status IN ('pending','running')`, so a cancelled row is never overwritten or retried, and the requeue sweep only touches `running`. A cancelled job is not active: it leaves the one-active-job index and the per-IP job count.
- **Crash recovery:** a periodic sweep returns `running` jobs whose `heartbeat_at` is older than N seconds to `pending` (`attempts + 1`), or marks them `failed` when `attempts >= max_attempts`.

## 9. `traces`: one row per request / job execution (observability)

| Column | Type | Notes |
|---|---|---|
| `trace_id` | uuid | **PK**; also returned in `meta.trace_id` and error bodies |
| `kind` | text | `CHECK in ('request','job')` |
| `created_at` | timestamptz | |
| `request` | jsonb | Sanitised request |
| `http_status` | integer | |
| `outcome` | text | `ok`, `no_matching_trials`, `rejected_by_policy`, `internal_error`, ... |
| `guard` | jsonb | Verdict, model, latency (reason stored for rejected requests, never returned) |
| `stages` | jsonb | Per-stage `{name, started_ms, duration_ms, status}` |
| `api_calls` | jsonb | `[{url, status, latency_ms, cache: hit|miss|revalidated, bytes}]` |
| `result_id` | uuid | Nullable |
| `job_id` | uuid | Nullable |

LLM calls are not duplicated here; they live as rows in `llm_usage` (section 10), linked by `trace_id`.

Index: `(created_at)` for retention and recent-trace queries. **No secrets or API keys are ever written.** Queries are stored as sent; no personal data is expected in this domain, but traces have a short retention.

## 10. `llm_usage`: one row per LLM call (usage and cost tracking)

This table exists because the public demo runs on **Cheiron's** OpenAI key, so every call's cost must be visible and capped.

| Column | Type | Notes |
|---|---|---|
| `call_id` | uuid | **PK** |
| `trace_id` | uuid | **FK -> traces** (nullable for calls outside a request, e.g. maintenance) |
| `job_id` | uuid | **FK -> jobs**, nullable |
| `stage` | text | `CHECK in ('guard','planner','narrator')` |
| `model` | text | Model actually used |
| `attempt` | integer | 1 = first try; >1 = retry |
| `is_fallback` | boolean | Served by the fallback model |
| `status` | text | `CHECK in ('ok','error','timeout')` |
| `input_tokens` | integer | From the provider's usage object |
| `cached_input_tokens` | integer | Prompt-cache hits (priced lower) |
| `output_tokens` | integer | |
| `reasoning_tokens` | integer | Reasoning models only (subset of output) |
| `latency_ms` | integer | |
| `cost_usd` | numeric(12,6) | Computed at write time from the price table |
| `price_version` | text | Which price-table version was used (so old rows stay explainable when prices change) |
| `created_at` | timestamptz | |

Indexes: `(created_at)`, `(model, created_at)`, `(trace_id)`.

*As built:* `attempt` and `status` were not built, and `trace_id` has no foreign key (`traces` is not built).

**Price table:** model prices are **not** hard-coded from memory. They live in a config file (`pricing.yaml`: per model, USD per 1M input / cached input / output tokens) with a `version` and a **"last verified" date**, filled in from OpenAI's official pricing page. An unknown model is logged with `cost_usd = null` and a warning, never silently priced at 0.

**Surfaced in:**
- each response: `meta.usage = { "llm_calls": 3, "input_tokens": ..., "output_tokens": ..., "cost_usd": 0.0042, "plan_cache_hit": true }`
- `GET /v1/usage?from=&to=&group_by=model|stage|day` (protected by an admin token): totals for calls, tokens, cost, error rate, fallback rate
- **savings:** plan-cache hits record the LLM calls avoided (`plan_cache.hit_count` × the original planner cost)

**Daily spending cap:** a configurable USD budget per day, checked against `SUM(cost_usd)` for the current day (UTC). When exceeded, new requests that need LLM calls get **503** `budget_exceeded` (cached results are still served). This protects the API key on the public endpoint.

*As built (2026-10-25):* "cached" means a stored plan for this exact request (`plan_cache`) **and** a stored result for that plan and citation options that is still valid or revalidates (Q8). Such a request makes no model call at all: not even the guard, because a plan is cached only after the guard passed that request (the plan-cache key covers the question and every field except the two citation options). Everything else, including a cached plan whose result would need a new narration, gets 503. Under the budget the guard still runs on every request.

## 11. `registry.trials` and `registry.sync_runs`: the mirror (Q22)

A copy of ClinicalTrials.gov for `fast` mode, in its own schema so it stays apart from the app's tables. The daily update and the first load are described in [Q22](22-term-sets.md#the-daily-update).

`registry.trials`, one row per study:

| Column | Type | Notes |
|---|---|---|
| `nct_id` | text | **PK** |
| `record` | jsonb | The study as the API returns it, limited to the fields the registry reads plus `LastUpdatePostDate` (no email fields) |
| `start_year` | integer | From `StartDate`; null when the trial has none. Indexed: the start-year slices of the load and the reconcile step |
| `last_update_post_date` | date | From `LastUpdatePostDate` |
| `synced_at` | timestamptz | When this row was last saved |

`registry.sync_runs`, one row per load or update:

| Column | Type | Notes |
|---|---|---|
| `run_id` | integer | **PK** |
| `kind` | text | `CHECK in ('load','update')` |
| `status` | text | `CHECK in ('running','succeeded','failed')`. **The last `succeeded` run's `data_timestamp` is the mirror's**: `fast` mode compares it with the API's current one |
| `data_timestamp` | timestamptz | The API's data the run brought the mirror to |
| `since` | date | Updates: the `LastUpdatePostDate` they fetched from |
| `upserted`, `removed` | integer | Trials saved and deleted |
| `error` | text | Why a failed run failed |
| `started_at`, `finished_at` | timestamptz | `started_at` minus three days is where the next update starts |

Index: `(status, finished_at)`. One sync at a time is enforced by a Postgres advisory lock, not a table.

## 12. `registry.term_sets` and `registry.term_members`: term sets (Q22)

The trials each search term matches, as the API resolved them, so the mirror never has to interpret a condition, drug, sponsor or place itself.

| Column | Type | Notes |
|---|---|---|
| `term_key` | text | **PK**, `"<param>|<expression>"`, such as `query.cond|"lung cancer"` |
| `param`, `expression` | text | The term's search parameter and Essie text |
| `size` | integer | Number of members |
| `data_timestamp` | timestamptz | The API data the members match |
| `resolved_at` | timestamptz | Last full listing (listed again after 7 days) |
| `checked_at` | timestamptz | Last listing or refresh; the next refresh asks for trials updated from three days before it |

`registry.term_members`: `term_key` (**FK -> term_sets**, cascade) and `nct_id` (text); primary key on both, index on `nct_id`.

## Retention and cleanup (periodic task)

| Data | Default retention |
|---|---|
| `results` (+ datums, citations via cascade) | `expires_at` (24 h) |
| `api_searches` (+ pages via cascade) | Unused for 7 days, **or** older than the revalidation safety ceiling (7 days, Q8) |
| `plan_cache` | Unused for 30 days, or `planner_version` no longer current |
| `jobs` | 24 h after finishing |
| `traces` | 30 days |
| `llm_usage` | 90 days (small rows; keeps cost history) |
| `data_versions` | Keep (tiny) |

**As built (2026-10-25): no cleanup task yet.** Expiry is logical: a result or job past `expires_at` is answered `410 expired` and is never reused, but nothing deletes the rows. `plan_cache` and `llm_usage` are kept indefinitely too. The `(expires_at)` index is ready for a periodic `DELETE`; at demo traffic the tables stay small. The mirror's tables are not subject to retention: they are the copy itself.

Rough size: a cached 1,000-study page (~2 MB raw) is ~0.2-0.3 MB compressed. 1,000 cached pages is ~250 MB. Fine for a single Postgres instance.

## What isn't in the database (by design)

- **Rate limiter state:** in-process for the single-instance submission (Q8, D8.5). In production it moves to Redis.
- **Secrets:** environment / secrets manager only.
- **A full mirror of studies:** not in the original design (Q6, revisited in [Q21](21-local-mirror-revisited.md)). **Superseded:** built later for `fast` mode, in the `registry` schema (sections 11-12, [Q22](22-term-sets.md)).

## Requirement links

P5 (citations storage and pagination), P6-1 (runnable), P7-2 (maintainable structure), P7-3, P7-8 (real-world data, robustness), P8-2 (traceability evidence).
