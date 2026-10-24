# System design: index

This folder records how the backend and web app are designed, one decision per file (Q1 to Q21). Each file states the decision, the reasons, the alternatives we considered and the assignment requirements it covers. Requirement IDs such as `P3-7` are defined in [`docs/parts/README.md`](../parts/README.md), and [`requirements-coverage.md`](requirements-coverage.md) maps each one to the decisions that cover it.

Most decisions were made on 2026-10-24, before and during the build. Later changes are recorded as dated revisions inside each file. Plans that were replaced stay in the files, marked **Superseded**, with a link to what replaced them. Where the build differs from the design, the file has an **As built** note.

## Decisions at a glance

| Q | File | Current decision |
|---|---|---|
| 1 | [01-scope.md](01-scope.md) | One question shape ("measure of trials matching filters, grouped by dimension(s) or linked as a network"); 9 question types, 7 chart types, 9 extra dimensions beyond the appendix. Efficacy, patient matching, single-trial summaries and stop-reason categorisation are out of scope |
| 2 | [02-pipeline.md](02-pipeline.md) | 12-stage pipeline; AI only in Guard, Plan and Narrate. The AI writes only the chart title, which code checks. The one-sentence summary was removed on 2026-10-24 (Q4b) |
| 3 | [03-ai-vs-code.md](03-ai-vs-code.md) | AI turns words into choices from fixed lists (incl. chart type); code turns choices into numbers. Planning is a **bounded agent with code tools** (`list_options`, `check_plan`, `count_trials`, `submit_plan`) plus a code gate |
| 4a | [04a-plan-schema.md](04a-plan-schema.md) | Strict QueryPlan: enums and bounded numbers everywhere except entity terms; 2-4 comparison groups; OR within a filter, AND across filters |
| 4b | [04b-ai-validation.md](04b-ai-validation.md) | 9 checks. Plan: schema, entity grounding, non-empty search, explained extra filters. Title: a **fact sheet + placeholders**, so numbers are correct by construction; number, name and banned-claim checks; one retry, then a template title. **Revised 2026-10-24:** the AI writes the title only; the summary is removed |
| 5 | [05-request-fields.md](05-request-fields.md) | Field names from the assignment (`drug_name`, `trial_phase`, ...); fields override the AI; bad input handled in 3 layers: 422, sanitise + escape, "no matching trials" with per-filter counts |
| 5b | [05b-input-guard.md](05b-input-guard.md) | AI guard for malicious requests, in parallel with planning; 400 on reject; **fail closed** after one retry (503) |
| 6 | [06-retrieval.md](06-retrieval.md) | **Live API only, exact answers.** Strategies S1 stats / S2 count per bucket / S3 fetch and aggregate; background jobs over ~60 s. Built: S3, and S2 for trials-per-year series (S1 and parallel slices are not built). A local mirror was rejected on 2026-10-24, then **revisited in Q21**, where search accuracy became the deciding reason |
| 7 | [07-query-compilation.md](07-query-compilation.md) | Strict matching by default (`InterventionNameSearch`, quoted `query.cond`); lead sponsor by default (`sponsor_role`); AST -> Essie with escaping; country alias table in code; exact API query in `meta` |
| 8 | [08-cache-ratelimit-retries.md](08-cache-ratelimit-retries.md) | Postgres cache (L1 API pages / L2 plans / L3 results; L1 not built); **revalidate, don't invalidate** on daily data updates (2 count calls); 40 req/min global limiter; retries with jittered backoff; circuit breaker; fallback model. Redis considered, deferred to production |
| 9 | [09-counting-rules.md](09-counting-rules.md) | Combined phase buckets (additive); once per distinct value for multi-valued dimensions; `meta.additive`, `unique_trials`, `counting_rule` |
| 10 | [10-missing-partial-estimated.md](10-missing-partial-estimated.md) | Nothing silently dropped (`meta.excluded`); "Not reported" bucket; time series end at the current year by default; estimated dates flagged; zero-fill; histogram overflow bin |
| 11 | [11-name-normalization.md](11-name-normalization.md) | Drugs and conditions grouped by MeSH (raw fallback), placebo excluded, no fuzzy sponsor merging; raw values always kept for citations. **Revised 2026-10-24:** each drug intervention takes only the MeSH term that matches its name |
| 12 | [12-io-schema.md](12-io-schema.md) | Own Vega-Lite-style schema (handles networks), `schema_version` `"2.0"` since the summary was removed; endpoints `/v1/query`, `/v1/jobs/{id}`, `/v1/results/{id}/citations`, `/v1/options`, `/v1/usage` (admin, Q16), `/health` |
| 13 | [13-networks.md](13-networks.md) | 6 network types; node and edge weights = distinct trials, plus Jaccard; deterministic pruning; communities; queried-entity highlight; investigator ↔ site from **site-level** contacts only |
| 14 | [14-citations.md](14-citations.md) | `{nct_id, url, title, evidence:[{field, excerpt}]}`; 5 per data point + paginated endpoint; `full` mode size-guarded; exactness check always on |
| 15 | [15-code-structure-stack.md](15-code-structure-stack.md) | Python 3.12, FastAPI, Pydantic v2, async httpx, SQLAlchemy + Alembic, **LangGraph** (the planner's tool loop), `uv`; registry-driven extension; Docker Compose with `postgres` + `api` + `web` and a one-command demo; no Redis. The original live-demo plan is superseded by Q19 |
| 16 | [16-database.md](16-database.md) + [ERD PDF](erd/schema.pdf) | 10 tables designed: revalidation-aware cache, immutable results, keyset-paginated citations, crash-safe jobs, traces, **`llm_usage`** (tokens, cost, daily budget cap). 7 built; the L1 page cache and `traces` are not |
| 17 | [17-error-handling.md](17-error-handling.md) | Non-chart outcomes are 200 + `status`; one error body; 422/400/404/410/429/503/500 codes incl. `budget_exceeded`; no silent partial answers |
| 18 | [18-testing.md](18-testing.md) | Unit, contract, integration (recorded API + fake AI), database, cross-check, AI evaluation (~40), **live end-to-end (~60 questions)**, smoke; CI on every push. Built: all offline layers, database tests, live cross-checks and a smaller end-to-end suite (the 9 appendix questions and more); the AI evaluation set is still to come |
| 19 | [19-deployment-ui.md](19-deployment-ui.md) | Next.js + ECharts reference UI (citations panel, "how we got this", raw JSON). **Deployed (revised 2026-10-25):** k3s on one EC2 t3.medium, Terraform + Kustomize, web and API at `trials.` / `api.cheiron.engineeradriel.com`, chosen for the deadline and cost (~$1.50/day). The original plan (Compose on EC2 behind Caddy, frontend on Vercel) is superseded. Production path: EKS multi-AZ, RDS, workers on KEDA, shared rate limiter, CloudFront + WAF, Argo CD |
| 20 | [20-model-selection.md](20-model-selection.md) | Model per AI stage chosen by a **measured bake-off** (quality bars, then lowest measured cost, then latency); official prices recorded. Defaults in use: guard and narrator `gpt-5.4-nano`, planner `gpt-5.4-mini`, fallback `gpt-4.1-mini` (different family). The bake-off has not run yet |
| 21 | [21-local-mirror-revisited.md](21-local-mirror-revisited.md) | Mirror **revisited after a broad question took 7 minutes, and still not built**: designed (same Postgres, `registry` schema, JSONB + indexed columns + child tables, daily delta sync), but a local copy can't reproduce the API's synonym and MeSH search (~20% of "lung cancer" trials missed). Routing structured-only questions to a mirror is the noted next step |

## Changelog

Dated revisions made after the first decision. Each one is recorded in full in the linked file.

| Date | Files | Change |
|---|---|---|
| 2026-10-24 | all | Consistency review before implementation (fixes listed below) |
| 2026-10-24 | [Q4b](04b-ai-validation.md#revision-2026-10-24-the-ai-summary-is-removed), Q2, Q3, Q12, Q17, Q20 | The AI summary under the chart title is removed after live testing; `schema_version` goes to `"2.0"` |
| 2026-10-24 | [Q11](11-name-normalization.md) | Each drug intervention takes only the MeSH term that matches its name or other names, so non-drug MeSH terms stay out of drug charts |
| 2026-10-24 | [Q13](13-networks.md) | Default minimum edge weight lowered from 2 to 1, so small scopes keep their links |
| 2026-10-25 | [Q21](21-local-mirror-revisited.md), Q6 | Local mirror revisited and still not built; search accuracy, not terms of use, is now the deciding reason |
| 2026-10-25 | [Q19](19-deployment-ui.md#revision-2026-10-25-what-was-actually-deployed), Q15 | Deployment revised: k3s on one EC2 instance with Terraform and Kustomize, instead of Compose behind Caddy with the frontend on Vercel |

### Consistency review (2026-10-24)

Before implementation, all design files were cross-checked against each other and against the API's metadata. These fixes were made:

| File | Fix |
|---|---|
| 06 | Cache storage stated as Postgres (was "Postgres or Redis"); job poll path `/v1/jobs/{id}`; job reuse now follows `request_key` + revalidation; the undecided client `async` flag became open item O1 |
| 04a, 05 | Options added in later decisions (phase mode, condition source, include unknown, show empty, edge metric, hide query entity, citations mode and count) added to the plan and request schemas |
| 07 | Made explicit: "recruiting" = trial overall status (site status is missing on 65% of sites) |
| 11, 13 | Investigator ↔ site corrected to use **site-level** contacts (`ContactRole` PI / sub-investigator); trial-level officials are no longer linked to every site (that would invent links) |
| 12 | Envelope now includes `schema_version`, `result_id`, `meta.usage`, `meta.citations`, `meta.network`, `meta.group_overlap`, `meta.cache`; 202 job and poll bodies defined |
| parts/06, assignment.md | Submission = zip + deployed endpoint; `gpt-4.1-nano` noted as retired |

Verified against `/studies/metadata`: every dimension added in Q1 maps to a real field (`eligibilityModule.stdAges`, `.sex`, `.healthyVolunteers`, `designInfo.allocation`, `maskingInfo.masking`, `designInfo.primaryPurpose`, `locations[].state`, `studyFirstPostDateStruct.date`, `hasResults`).

## Decision log: open items from the design phase

These items were left open when the design was written, because they needed a decision or a live check during implementation.

| # | Item | Resolution | Status |
|---|---|---|---|
| O1 | Client `async` flag on `/v1/query` | **No flag.** Sync or async is chosen only by the server's estimate ([Q6](06-retrieval.md#background-jobs)) | Resolved |
| O2 | Models per AI stage | Selection process decided in [Q20](20-model-selection.md); prices verified 2026-10-24. Defaults in use: guard `gpt-5.4-nano`, planner `gpt-5.4-mini`, narrator `gpt-5.4-nano`, fallback `gpt-4.1-mini`. The measured comparison (bake-off) is still to come; it needs the AI evaluation set ([Q18](18-testing.md)) | Defaults in use, comparison pending |
| O3 | Public-endpoint limits | All limits exist, are configurable and documented, with **high defaults** that don't restrict realistic use ([Q19, "Configurable limits"](19-deployment-ui.md#configurable-limits-open-item-o3)). Implemented in [`backend/app/core/config.py`](../../backend/app/core/config.py) | Resolved |
| O4 | `/stats/field/values` counting semantics and the top-250 cap (strategy S1) | Live check not done. Not needed today: S1 is not built ([Q6](06-retrieval.md)). Required before S1 is built | Open (live check) |
| O5 | Does every visible change bump `LastUpdatePostDate`? (revalidation, Q8) | Live check not done. Until it is, the 7-day safety ceiling applies, and it is implemented ([Q8](08-cache-ratelimit-retries.md)) | Open (live check) |
| O6 | Real ClinicalTrials.gov rate limit (careful ramp test) | Live check not done, on purpose: it risks getting blocked ([live probe §8](../api/live-probe.md)). The global limiter stays at a conservative 40 requests/min | Open (live check, last) |
| O7 | README outline, incl. the Part 8 integrity section (tools used, validation, designed vs generated) | The [README](../../README.md) is written: running it, the API, real example runs, key design decisions, testing and validation, limitations and deployment | Resolved |
| O8 | DNS record for the API | Done. `trials.cheiron.engineeradriel.com` and `api.cheiron.engineeradriel.com` are A records in Route 53, managed by Terraform; the deployment is live ([Q19 revision](19-deployment-ui.md#revision-2026-10-25-what-was-actually-deployed)). The original item named `api.engineeradriel.com` for the superseded Caddy plan | Resolved |
