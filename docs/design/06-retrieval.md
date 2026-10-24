# Design Q6: How we get the data (retrieval strategy)

Status: **Decided** (2026-10-24)

## Decisions

| # | Decision |
|---|---|
| D6.1 | **Live data only.** Every answer is computed from the ClinicalTrials.gov API at request time (or from a cache of API responses). We do **not** mirror the full dataset locally. |
| D6.2 | **Exact answers, no sampling.** We fetch the full relevant data for a question; we never estimate from a sample. |
| D6.3 | **Cache** API responses (and, optionally, computed results) in **Postgres** (decided in Q8; Redis considered, see Q8/Q15). **Kept correct across the API's daily data updates** by tracking `dataTimestamp` (from `/version`) and **revalidating** cached searches with two cheap count calls instead of discarding everything (revised design in Q8). |
| D6.4 | **Parallel slice fetching** with configurable concurrency (**default 2**), used only when the result is large enough to justify it. |
| D6.5 | **Background jobs** for requests estimated to take **over ~60 s**: the API returns a job ID immediately; the client polls for the result. Job state is stored in the database. |
| D6.6 | Retrieval sits behind a **data-source interface**, so a local mirror with incremental sync could be added later without changing other stages (documented as future work). |

**As built (2026-10-25):** strategy S3 (fetch and aggregate) answers most questions, and S2 answers trials-per-year series with one count call per year. Comparison groups are fetched concurrently through the shared rate limiter. Strategy S1 (`/stats/field/values`) and parallel slices within one search are designed below but not built. Code: [`backend/app/pipeline/run.py`](../../backend/app/pipeline/run.py), [`backend/app/ctgov/retrieval.py`](../../backend/app/ctgov/retrieval.py).

## Why live

> **Updated 2026-10-25:** the mirror question was reopened in [Q21](21-local-mirror-revisited.md). Live retrieval still stands, but the main reason changed. Q21 found strong precedent for mirroring (ClinicalTrials.gov offers full downloads, and AACT publishes a daily Postgres copy), so the terms of use are no longer the deciding factor. The deciding factor is **search accuracy**: the API resolves drug and condition synonyms, and a plain local copy can't yet. The reasons below are the original ones from 2026-10-24.

1. **Terms of use not yet checked** for bulk-copying the dataset, while live use of the public API is clearly intended.
2. **Simplicity:** no ingestion job, no multi-GB database, simpler deployment and review.
3. **Authority:** every number comes from the authoritative API at request time.

## Alternative we weighed seriously: a local mirror of the full dataset

This option got real design time before we chose live retrieval. It is recorded here so the reasoning is visible. [Q21](21-local-mirror-revisited.md) revisits it with a fuller design and a new finding.

**The design:**
- Download all ~608k studies once through the API (`/studies`, 1,000 per page, ~608 pages, ~20-30 min at a safe rate) into Postgres.
- Store each study's **raw JSON exactly as returned** (so citations stay exact) plus extracted columns for querying.
- Keep it fresh with an **incremental daily sync**: `filter.advanced=AREA[LastUpdatePostDate]RANGE[<last sync>,MAX]` fetches only studies changed since the last sync.
- A periodic ID-only pass (`fields=NCTId`) detects removed studies.
- Answer every question with SQL over the mirror.

**What it would have given us:**

| Benefit | Detail |
|---|---|
| Exact answers for **any** scope in < 1 s | Including unscoped networks/histograms over all 608k trials, which live retrieval can only do as a background job |
| No per-request API load | Rate limits only matter for the sync job |
| Same freshness as the live API | The API itself refreshes once a day (Mon-Fri), so a daily incremental sync loses nothing |
| Relevant to the role | Large-scale ingestion is a core responsibility in the role this project was built for |

**Why we rejected it (2026-10-24, for this submission):**

| Reason | Weight |
|---|---|
| **Terms of use** for bulk-copying the dataset were not yet checked; live use of the public API is clearly intended. | Main reason at the time. Since [Q21](21-local-mirror-revisited.md), secondary: precedent for mirroring is strong, and search accuracy is the deciding reason |
| **Complexity and deployment weight:** an ingestion job, scheduling, a multi-GB database that must be built before first use, and sync-failure handling | High |
| **Authority:** live retrieval means every number comes from the authoritative API at request time, which is simple to explain and to verify | Medium |
| ~~Staleness~~ | **Not** a valid reason. A full daily re-download would have been needed without the incremental sync above, which solves it. Recorded so it isn't misstated. |

**When to revisit:**
- the terms of use are confirmed to allow mirroring, **or**
- unscoped per-trial questions become common enough that background jobs are too slow for users.

The data-source interface (D6.6) makes this a contained change.

**Revisited on 2026-10-25** after a broad question took about 7 minutes: see [Q21](21-local-mirror-revisited.md). Still not built. The deciding issue is search accuracy: the API resolves synonyms, and a local copy can't yet. [Q22](22-term-sets.md) proposes a second, opt-in `fast` mode that keeps the API's search for membership and uses the mirror only for records; live retrieval stays the default.

## How a request is fetched

1. **Size first:** one cheap `countTotal` call (~0.35 s) per search tells us how many studies match, hence how many pages, before we fetch anything.
2. **Pick a strategy per question** (all exact):

| Strategy | When | Calls |
|---|---|---|
| **S1. Global stats** (`/stats/field/values`) | Unscoped, single categorical dimension (phase, status, country, sponsor class, ...) | 1 (**to verify:** counting semantics, top-250 cap) |
| **S2. Count per bucket** (`countTotal` per category) | Categorical/time dimension with a known, bounded set of values, especially large scopes | one per bucket |
| **S3. Fetch and aggregate** (minimal `fields`) | Everything that needs per-trial data: networks, histograms, scatter, enrollment measures, open-ended top-N, citations | one per 1,000 trials |

3. **Estimate the duration** from the page/call count, the rate limit and the concurrency. **<= ~60 s** -> answer synchronously; **> ~60 s** -> background job.

### Parallel slice fetching

- Pages of **one** search can't be fetched in parallel (each page needs the previous page's `nextPageToken`).
- So a large search is split into **independent slices**, each a separate search with an extra filter, e.g. start-year ranges `AREA[StartDate]RANGE[2015-01-01,2017-12-31]`, plus one slice for studies with no start date (`AREA[StartDate]MISSING`). Slices are paginated independently and run concurrently.
- **Exactness check:** the sum of the slice `totalCount`s must equal the unsliced `totalCount`, and NCT IDs are de-duplicated. On a mismatch, refetch or fail loudly.
- Slicing only applies above a threshold (configurable, e.g. > 3 pages). Small searches use a single sequential stream.
- **All calls share one global rate limiter** (Q8), so parallelism never exceeds the API budget.

### Citations with S1/S2

S1/S2 return counts only, so we can't produce per-trial citations for those values directly. Options (decided in Q14):
- cite the exact **API query** that produced each count (reproducible), and/or
- fetch a small sample of NCT IDs per bucket (`pageSize` = N), which costs extra calls.

## Background jobs

| Item | Design |
|---|---|
| Trigger | Estimated duration > ~60 s (configurable). Sync vs async is decided **only by the server's estimate**. There is **no client `async` flag** (open item O1, decided no): one predictable behaviour, fewer API states. |
| Response | `202 Accepted` + `{ job_id, status: "pending", poll_url, estimated_seconds }` |
| Poll | `GET /v1/jobs/{job_id}` -> `pending` / `running` (with progress: pages done / total) / `succeeded` (with the normal visualization response) / `failed` (structured error) |
| Storage | `jobs` table in Postgres: id, request, plan, status, progress, result JSON, error, created/started/finished timestamps, data_timestamp |
| Worker | In-process async worker pool for the assignment (configurable size); a separate worker service is future work |
| Reuse | An identical request (same `request_key`) returns the existing active job (partial unique index, Q16) or a still-valid stored result (revalidated, Q8) instead of starting a new one |
| Retention | Results kept for a configurable time (e.g. 24 h, or until the data updates) |
| Cancel | `DELETE /v1/jobs/{job_id}` (added 2026-10-25, see the revision below) |

**Revision (2026-10-25): jobs can be cancelled.** A broad job used to run to the end with nobody waiting (an unscoped question is ~15 min of the shared 40 requests/min). `DELETE /v1/jobs/{job_id}` sets a `pending` or `running` job to `cancelled` (`error.code` `cancelled`); a finished job is returned unchanged, so the call is idempotent. The worker checks the row after every page and, for stages without page progress (per-year counts, aggregation, narration), every second, then cancels its work: it stops within about one page (~1.5 s) and writes nothing more. Requests it had queued in the rate limiter leave the queue, freeing the shared budget. A cancelled job is never retried or requeued. Anyone holding the `job_id` may cancel, the same trust model as polling (an unguessable UUID). A synchronous request is not cancellable: if the client disconnects, the server finishes, stores the answer and reuses it for a repeat; the web app's Stop button cancels a job whose 202 arrives after Stop. Tests: `backend/tests/db/test_job_cancel.py`.

## Rough durations (from live probing; rate limit assumed 40 req/min)

| Question | Pages | Conservative | If ~3 req/s |
|---|---|---|---|
| Drug-scoped (~3k trials) | 3 | ~5 s | ~3 s |
| Broad condition (~17k) | 17 | ~27 s | ~8 s |
| Two broad conditions (~32k) | 32 | ~50 s | ~15 s |
| Very broad term (100k+, unverified) | 100+ | 2.5+ min -> **job** | ~50 s |
| Unscoped, needs per-trial data (608k) | 609 | ~15 min -> **job** | ~5 min -> **job** |

Unscoped categorical questions avoid this cost through S1/S2.

**Revision (2026-10-25): measured limit, and the quicker strategy.** The real limit is ~10 requests per ~10 s ([live probe §8](../api/live-probe.md)), and the limiter now allows a burst of 9, so the S2 count calls of a question mostly start at once. Pages still come one by one (page tokens), so the column "Conservative" above stays about right for S3. A trials-per-year series now uses S2 only when its count calls are quicker than downloading its pages: 30 trials over 20 years is one page, not 61 calls.

## Requirement links

P2-1, P2-2 (authoritative live source), P1-3 (retrieve relevant data), P7-1..P7-3 (rational design, real-world data), P7-8 (robustness).
