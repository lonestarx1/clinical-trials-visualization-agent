# System Design: Index

Designed with the user, one question at a time, on 2026-10-24. Each file records the decision, the reasons, the alternatives considered and the requirement links. Requirement coverage: [`requirements-coverage.md`](requirements-coverage.md).

## Decisions at a glance

| Q | File | Decision in one line |
|---|---|---|
| 1 | [01-scope.md](01-scope.md) | One question shape ("measure of trials matching filters, grouped by dimension(s) or linked as a network"); 9 question types, 7 chart types, 9 extra dimensions beyond the appendix; efficacy, patient matching, single-trial summaries and stop-reason categorisation out of scope |
| 2 | [02-pipeline.md](02-pipeline.md) | 12-stage pipeline; AI only in Guard, Plan and Narrate; AI writes the title, validated (the one-sentence summary was removed 2026-10-24, see Q4b) |
| 3 | [03-ai-vs-code.md](03-ai-vs-code.md) | AI turns words into choices from fixed lists (incl. chart type); code turns choices into numbers. Planning is a **bounded agent with code tools** (`list_options`, `check_plan`, `count_trials`, `submit_plan`) + a code gate |
| 4a | [04a-plan-schema.md](04a-plan-schema.md) | Strict QueryPlan: enums/bounded numbers everywhere except entity terms; 2-4 comparison groups; OR within a filter, AND across filters |
| 4b | [04b-ai-validation.md](04b-ai-validation.md) | 9 checks: schema, entity grounding, non-empty search, explained extra filters; **fact sheet + placeholders** so narrated numbers are correct by construction; number/name/banned-claim checks; retry then template fallback. **Revised 2026-10-24:** AI writes the title only, the summary is removed |
| 5 | [05-request-fields.md](05-request-fields.md) | PDF field names (`drug_name`, `trial_phase`, ...); fields override the AI; bad input in 3 layers: 422, sanitise + escape, "no matching trials" with per-filter counts |
| 5b | [05b-input-guard.md](05b-input-guard.md) | AI guard for malicious requests, in parallel with planning; 400 on reject; **fail closed** after one retry (503) |
| 6 | [06-retrieval.md](06-retrieval.md) | **Live API only, exact answers**; strategies S1 stats / S2 count per bucket / S3 fetch + aggregate; parallel slices (concurrency 2); background jobs over ~60 s. Local mirror **seriously weighed and rejected** (legal uncertainty, complexity, authority) |
| 7 | [07-query-compilation.md](07-query-compilation.md) | Strict matching by default (`InterventionNameSearch`, quoted `query.cond`); lead sponsor by default (`sponsor_role`); AST -> Essie with escaping; country alias table in code; exact API query in `meta` |
| 8 | [08-cache-ratelimit-retries.md](08-cache-ratelimit-retries.md) | Postgres cache (L1 API / L2 plans / L3 results); **revalidate, don't invalidate** on daily data updates (2 count calls); 40 req/min global limiter; retries with jittered backoff; circuit breaker; fallback model. Redis considered, deferred to production |
| 9 | [09-counting-rules.md](09-counting-rules.md) | Combined phase buckets (additive); once-per-distinct-value for multi-valued dimensions; `meta.additive`, `unique_trials`, `counting_rule` |
| 10 | [10-missing-partial-estimated.md](10-missing-partial-estimated.md) | Nothing silently dropped (`meta.excluded`); "Not reported" bucket; time series end at the current year by default; estimated dates flagged; zero-fill; histogram overflow bin |
| 11 | [11-name-normalization.md](11-name-normalization.md) | Drugs and conditions grouped by MeSH (raw fallback), placebo excluded, no fuzzy sponsor merging; raw values always kept for citations |
| 12 | [12-io-schema.md](12-io-schema.md) | Own Vega-Lite-style schema (handles networks); endpoints `/v1/query`, `/v1/jobs/{id}`, `/v1/results/{id}/citations`, `/v1/options`, `/v1/usage`, `/health` |
| 13 | [13-networks.md](13-networks.md) | 6 network types; node/edge weights = distinct trials + Jaccard; deterministic pruning; communities; queried-entity highlight; investigator ↔ site from **site-level** contacts only |
| 14 | [14-citations.md](14-citations.md) | `{nct_id, url, title, evidence:[{field, excerpt}]}`; 5 per data point + paginated endpoint; `full` mode size-guarded; exactness check always on |
| 15 | [15-code-structure-stack.md](15-code-structure-stack.md) | Python 3.12, FastAPI, Pydantic v2, async httpx, SQLAlchemy + Alembic, **LangGraph**, `uv`; registry-driven extension; Docker Compose with `postgres` + `api` + `web` and one-command demo; no Redis in the submission |
| 16 | [16-database.md](16-database.md) + [ERD PDF](erd/schema.pdf) | 10 tables incl. revalidation-aware cache, immutable results, keyset-paginated citations, crash-safe jobs, traces, **`llm_usage`** (tokens, cost, daily budget cap) |
| 17 | [17-error-handling.md](17-error-handling.md) | Non-chart outcomes are 200 + `status`; one error body; 422/400/404/410/429/503/500 codes incl. `budget_exceeded`; no silent partial answers |
| 18 | [18-testing.md](18-testing.md) | Unit, contract, integration (recorded API + fake AI), database, cross-check, AI eval (~40), **live end-to-end (~60 questions)**, smoke; CI on every push |
| 19 | [19-deployment-ui.md](19-deployment-ui.md) | Next.js + ECharts reference UI (citations panel, "how we got this", raw JSON). **Deployed (revised 2026-10-25):** k3s on one EC2 t3.medium, Terraform + Kustomize, web and API at `trials.` / `api.cheiron.engineeradriel.com`, chosen for the deadline and cost (~$1.50/day); production path: EKS multi-AZ, RDS, workers on KEDA, shared rate limiter, CloudFront + WAF, Argo CD |
| 20 | [20-model-selection.md](20-model-selection.md) | Model per AI stage chosen by a **measured bake-off** (quality bars, then lowest measured cost, then latency); official prices recorded; starting defaults guard/narrator `gpt-5.4-nano`, planner `gpt-5.4-mini`, fallback `gpt-4.1-mini` (different family) |
| 21 | [21-local-mirror-revisited.md](21-local-mirror-revisited.md) | Mirror **revisited after a 7-minute broad question, still not built**: designed (same Postgres, `registry` schema, JSONB + indexed columns + child tables, daily delta sync), but a local copy can't reproduce the API's synonym/MeSH search (~20% of "lung cancer" trials missed). Hybrid routing of structured-only questions noted as the next step |

## Fixes made in the consistency review (2026-10-24)

| File | Fix |
|---|---|
| 06 | Cache storage stated as Postgres (was "Postgres or Redis"); job poll path `/v1/jobs/{id}`; job reuse now follows `request_key` + revalidation; the undecided `async` flag moved to open items |
| 04a, 05 | Options added later (phase mode, condition source, include unknown, show empty, edge metric, hide query entity, citations mode/count) added to the plan and request schemas |
| 07 | Made explicit: "recruiting" = trial overall status (site status missing on 65% of sites) |
| 11, 13 | Investigator ↔ site corrected to use **site-level** contacts (`ContactRole` PI / sub-investigator); trial-level officials are no longer linked to every site (that would invent links) |
| 12 | Envelope now includes `schema_version`, `result_id`, `meta.usage`, `meta.citations`, `meta.network`, `meta.group_overlap`, `meta.cache`; 202 job and poll bodies defined |
| parts/06, assignment.md | Submission = zip + deployed endpoint; `gpt-4.1-nano` noted as retired |

Verified against `/studies/metadata`: every dimension added in Q1 maps to a real field (`eligibilityModule.stdAges`, `.sex`, `.healthyVolunteers`, `designInfo.allocation`, `maskingInfo.masking`, `designInfo.primaryPurpose`, `locations[].state`, `studyFirstPostDateStruct.date`, `hasResults`).

## Open items (need a decision or a live check before / during implementation)

| # | Item | Type |
|---|---|---|
| O1 | Client `async` flag on `/v1/query` | **Decided: no.** Sync/async is chosen by the server's estimate only (Q6) |
| O2 | Models per AI stage | **Decided (process):** see [20-model-selection.md](20-model-selection.md). Starting defaults guard `gpt-5.4-nano`, planner `gpt-5.4-mini`, narrator `gpt-5.4-nano`, fallback `gpt-4.1-mini`; prices verified 2026-10-24; final picks from a measured bake-off |
| O3 | Public-endpoint limits | **Decided:** all limits exist, are configurable and documented, with **high defaults** that don't restrict realistic use (see `19-deployment-ui.md`, "Configurable limits") |
| O4 | `/stats/field/values` counting semantics and the top-250 cap (strategy S1) | Live check |
| O5 | Does every visible change bump `LastUpdatePostDate`? (revalidation, Q8) | Live check |
| O6 | Real ClinicalTrials.gov rate limit (careful ramp test) | Live check, **last** (risk of being blocked) |
| O7 | README outline, incl. the Part 8 integrity section (tools used, validation, designed vs generated) | Implementation plan |
| O8 | DNS `A` record for `api.engineeradriel.com` | User action (confirm provider first) |
