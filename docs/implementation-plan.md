# Implementation Plan

Status: **Draft** (2026-10-24 19:30 KST), for review with the user.

## Deadline

Sun 2026-10-25 15:00 KST (Ashby).

The design (Q1-Q20) is the target. It is larger than the time available, so every milestone ends with `main` **runnable and submittable**, and lower-priority pieces have explicit cut lines. Anything designed but not built is listed honestly in the README ("Designed, not built").

## Rules for every milestone

- One branch + one PR per milestone (or per half-milestone), small Conventional Commits, merged with a merge commit.
- **Test-first (see below).** CI (lint + tests) must pass before merging.
- The README is updated in the same PR when the milestone changes how to run or what's supported.
- No live ClinicalTrials.gov calls in CI. Integration tests use recorded responses (Q18).

## Test-first development (TDD)

Tests are written **before** the code they cover, one small unit at a time (red -> green -> refactor), not as one big upfront test suite. The commit history shows it: a `test:` commit with failing tests, then the `feat:` commit that makes them pass.

| Layer | What is written first | Expected values come from |
|---|---|---|
| **Acceptance** (start of each milestone) | The milestone's exit check as tests, marked `xfail` until the milestone delivers them; e.g. PA-1..PA-9 as request -> expected plan properties and chart type | Requirement IDs, design docs |
| **Unit** (deterministic core) | Compiler (plan -> exact Essie string), counting rules, normalisation, aggregation, chart builders, citation exactness, error mapping | Design decisions (Q7, Q9-Q14, Q17) + the probe samples |
| **Contract** | Request/response schemas, error bodies, the envelope invariants (e.g. one citation list per datum) | Q5, Q12, Q17 |
| **Integration** | End-to-end through the pipeline with recorded API responses and a fake LLM | Probe samples + hand-checked expected outputs |
| **AI stages** | The eval cases (questions -> expected plan properties; malicious vs harmless inputs; fact sheets -> checks) before the prompts are written | Q18, Q20 |

Rules:
- **Expected values are worked out independently** (by hand from the sample JSON or from a direct API count), never copied from the code's own output.
- A bug found later gets a failing test first, then the fix.
- Live API and live LLM tests are separate, opt-in suites (`make test-live`), never in CI.

## Milestones

"Exit check" is what must be true before the PR merges.

### M0: Skeleton

- `backend/`: uv project, Python 3.12, FastAPI app, Pydantic Settings (all env vars from Q19/Q20 with defaults), structured logging, `GET /health`.
- `docker-compose.yml` with `postgres` + `api`; `Makefile` (`make up`, `make test`, `make lint`).
- GitHub Actions: ruff + pytest.
- Test harness: pytest layout (`unit/`, `contract/`, `integration/`, `live/`), fixtures loader for the probe samples, fake LLM, and the **acceptance tests for PA-1..PA-9 written now** (`xfail` until M2).
- **Exit check:** `make up` starts both containers and `/health` returns 200 (tested first); CI is green.

### M1a: Data layer, no AI

- `registry/`: dimensions, measures, chart types (declarative, Q15).
- `schemas/`: request, QueryPlan, response envelope (Q4a, Q5, Q12).
- `ctgov/`: async client with the global rate limiter (40/min, concurrency 2), jittered retries, circuit breaker; plan AST -> Essie compiler with escaping (Q7); strategies S2 (count per bucket) and S3 (fetch + aggregate) (Q6).
- Recorded API fixtures from the probe samples.
- **Exit check:** unit tests for the compiler and client; an integration test turns a hand-written QueryPlan into the correct API calls.

### M1b: Normalize, aggregate, chart

- `pipeline/`: normalize (Q11, MeSH grouping), aggregate with counting rules and `excluded` counts (Q9, Q10), chart builders for **bar, grouped bar, time series, histogram, metric**.
- Sampled citations per datum with the exactness check (Q14).
- `POST /v1/query` accepts a **QueryPlan directly** (debug path), so the whole non-AI pipeline can be checked end to end.
- **Exit check:** PA questions expressible as plans produce correct charts against recorded data; cross-check test vs direct API counts (Q18).

### M2: AI stages  ->  first submittable version

- LangGraph state graph (Q15). Planner agent with `list_options`, `check_plan`, `count_trials`, `submit_plan`, step limit, plan gate (Q3, Q4b).
- Guard in parallel, fail closed (Q5b). Narrator with fact sheet + placeholders and checks V6-V8, template fallback (Q4b).
- Error codes and bodies (Q17). Fake LLM for integration tests.
- README v1: run, request/response schemas, design summary, limitations; **3-5 example runs with real JSON** (`docs/examples/`).
- **Exit check:** the assignment's example request works; PA-1..PA-9 attempted live, results recorded. **Every MUST requirement is met at this point.**

### M3: Networks, scatter, citations endpoint

- Network builders (Q13): sponsor-collaborator, drug co-occurrence, condition-drug at minimum; Jaccard, pruning, communities.
- Scatter chart. `GET /v1/results/{id}/citations` with keyset paging (Q14).
- **Exit check:** PA network questions return meaningful graphs with node and edge citations.

### M4: Persistence, cache, jobs, usage

- SQLAlchemy models + Alembic for the Q16 tables, in priority order: `results`, `result_datums`, `result_citations`, `llm_usage` (+ daily budget), `api_pages` (L1), `jobs`, `plan_cache` (L2), `traces`.
- Revalidation (Q8), background jobs above `SYNC_MAX_SECONDS`, `GET /v1/jobs/{id}`, `/v1/usage`, `/v1/options`.
- **Exit check:** a repeat question is served from cache after revalidation; a broad question becomes a job and completes.

### M5: Frontend

- `frontend/`: Next.js + ECharts renderer for all chart types, field pickers from `/v1/options`, citations panel, "how we got this", raw JSON toggle, job progress (Q19). Added to Compose as `web`.
- **Exit check:** `make up` opens a working app.

### M6: Deploy

- IaC stack (CloudFormation or CDK): EC2, Elastic IP, security group, instance role, Secrets Manager for the OpenAI key. Caddy HTTPS at `api.engineeradriel.com` (DNS needs the user, O8). Vercel for `frontend/`.
- **Exit check:** the public endpoint answers the example request over HTTPS.

### M7: Evaluation and final README

- AI eval set (~40) + live E2E (~60) with the report in `docs/eval/`; a reduced bake-off (planner first) (Q18, Q20).
- Live checks O4, O5, then O6 (rate-limit ramp) **last**.
- README final: Part 8 integrity section (tools used, how correctness was validated, designed vs generated) (O7), measured costs, "Designed, not built".
- **Submit:** zip, final check from a clean clone, submit on Ashby.

## Submittable checkpoints

| After | What a reviewer gets |
|---|---|
| M2 | Every MUST: NL query -> validated plan -> live data -> chart spec with citations; README + example runs |
| M4 | + networks, scatter, citation paging, cache, jobs, cost tracking |
| M6 | + UI and public endpoint |
| M7 | + measured evaluation and model choice |

## Cut lines (dropped in this order if behind)

1. Demo video
2. Bake-off beyond the planner (other stages keep their starting defaults, stated in the README)
3. Network types beyond the three listed in M3
4. `plan_cache` (L2) and `traces` tables (traces stay in logs and `meta`)
5. Frontend extras: field pickers, job progress (keep chart + citations + raw JSON)
6. Deployment (M6): the zip stays fully runnable locally

Never cut: input validation, the plan gate, narration checks, citation exactness, honest `excluded` / `could_not_interpret` handling, tests for the deterministic core, the Part 8 README section.

## Risks

| Risk | Mitigation |
|---|---|
| Planner quality below the bar | Tool feedback + gate first; bigger model only as a last resort (Q20) |
| ClinicalTrials.gov throttling during development | Recorded fixtures; global limiter; O6 test last |
| Broad questions too slow | S2 counts before S3 fetches; jobs; page cap with an explicit error, never a silent partial answer |
| DNS / Vercel setup delays | M6 is late and cuttable; local `make up` is the primary path |
| Time overrun | Checkpoints above; cut lines decided in advance |
