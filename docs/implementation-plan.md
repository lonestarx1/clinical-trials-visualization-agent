# How it was built

This document describes how the project was built: the order of work, the test-first workflow, the milestones and what each one delivered, and what's still planned.

The work ran in this order:

1. **Requirements:** the assignment was transcribed and broken into atomic requirements ([`docs/parts/`](parts/README.md)).
2. **API research:** the ClinicalTrials.gov documentation was read ([contract](api/contract.md)), then the live API was probed ([live probe](api/live-probe.md)).
3. **System design:** design decisions Q1 to Q20, one question at a time ([`docs/design/`](design/README.md)). Q21 was added during the build.
4. **Build:** the milestones below, each one a pull request.

The design was larger than the time available, so the build had two safeguards. Every milestone left `main` runnable, and lower-priority pieces had cut lines decided in advance. Anything designed but not built is listed in the README's [limitations](../README.md#limitations).

## Working rules

- One branch and one pull request per milestone (or half-milestone), with small [Conventional Commits](https://www.conventionalcommits.org/), merged with a merge commit.
- CI (lint, type check and tests) passes before a merge.
- The README is updated in the same pull request when a milestone changes how to run the project or what it supports.
- CI makes no live ClinicalTrials.gov or model calls. Integration tests use recorded API responses and scripted fake models ([design Q18](design/18-testing.md)).

## Test-first development

Tests are written **before** the code they cover, one small unit at a time (red, green, refactor), not as one big test suite up front. The commit history shows it: a `test:` commit with failing tests, then the `feat:` commit that makes them pass.

| Layer | What is written first | Expected values come from |
|---|---|---|
| **Acceptance** (start of each milestone) | The milestone's exit check as tests, marked `xfail` until the milestone delivers them; e.g. the 9 appendix questions (PA-1 to PA-9) as request -> expected plan properties and chart type | Requirement IDs, design docs |
| **Unit** (deterministic core) | Compiler (plan -> exact Essie string), counting rules, normalisation, aggregation, chart builders, citation exactness, error mapping | Design decisions (Q7, Q9-Q14, Q17) and the probe samples |
| **Contract** | Request and response schemas, error bodies, the envelope invariants (e.g. one citation list per data point) | Q5, Q12, Q17 |
| **Integration** | The whole pipeline with recorded API responses and a fake model | Probe samples and hand-checked expected outputs |
| **AI stages** | The checks around each AI stage (gate rules, narration checks) with scripted fake models | Q4b, Q5b |

Rules:

- **Expected values are worked out independently**, by hand from the sample JSON or from a direct API count, never copied from the code's own output.
- A bug found later gets a failing test first, then the fix. For example, the hand counts in two network tests were wrong; they were corrected in their own `test:` commits.
- Live API and live model tests are separate, opt-in suites (`make test-live`, `make test-e2e`), never run in CI.

## Milestones

Each milestone had an **exit check**: what had to be true before its pull request merged. Test counts are the offline suite at the time of the merge.

| Milestone | Delivered | Offline tests |
|---|---|---|
| M0: Skeleton | FastAPI app, settings, `/health`, Docker Compose, CI | 20 |
| M1a: Data layer | Registry, schemas, query compiler, ClinicalTrials.gov client | 163 |
| M1b: Normalize, aggregate, chart | Extraction, counting rules, 5 chart types, citations, debug endpoint | 208 |
| M2: AI stages | Guard, planner agent, gate, narrator, `POST /v1/query`, examples | 290 |
| M3: Networks and scatter | Network graphs, scatter plots, series splits | 315 |
| M4: Persistence | Stored results, full citations, caches, background jobs, cost tracking | 318 (+16 database) |
| M5: Frontend | Next.js and ECharts web app | 8 web |
| M6: Deploy | Terraform and k3s on AWS, live over HTTPS | |

### M0: Skeleton

- **Planned:** a `uv` project on Python 3.12 with FastAPI, typed settings for every limit and model, structured logging and `GET /health`; Docker Compose with `postgres` and `api`; a `Makefile`; CI with ruff and pytest; the test layout and the acceptance tests for the appendix questions, marked as expected failures.
- **Delivered:** all of that, plus mypy (strict) and database tests in CI. `/health` returns 503 when Postgres is down.
- **Changed:** the fake model moved to M2, where the model interface it fakes was built.
- **Exit check:** `make up` starts both containers and `/health` returns 200.

### M1a: Data layer, no AI

- **Delivered:**
  - A declarative **registry** of 25 dimensions (categorical, entity, time, numeric), each with its API fields, filter, enum and counting rule, plus measures, chart types and intents ([Q15](design/15-code-structure-stack.md)).
  - Strict request and plan **schemas**.
  - An **Essie expression tree** where request text can only enter as one quoted phrase, and a **compiler** from plan to API parameters ([Q7](design/07-query-compilation.md)).
  - An async **client** with a shared rate limiter (40 requests/min, 2 in flight; since measured and raised to 9 per 10 s, 9 in flight), jittered retries that honour `Retry-After`, a circuit breaker, and page-token paging with a result-count check ([Q6](design/06-retrieval.md), [Q8](design/08-cache-ratelimit-retries.md)).
  - Count-per-bucket retrieval with an exactness check.
- **Exit check:** an integration test turns hand-written plans for three appendix questions into the exact expected API calls.
- **Live checks:** query escaping holds on the real API (an injection attempt matches fewer than 100 trials, not all ~600k), every filter narrows the results, and study-type buckets add up exactly.

### M1b: Normalize, aggregate, chart

- **Delivered:**
  - **Extraction** of each dimension's values from the raw study JSON, keeping the exact JSON path and excerpt for every value. MeSH grouping for drugs and conditions, with a cleaned-name fallback that skips placebo ([Q11](design/11-name-normalization.md)).
  - **Aggregation** with explicit counting rules, a "Not reported" bucket, and counts of everything excluded ([Q9](design/09-counting-rules.md), [Q10](design/10-missing-partial-estimated.md)).
  - **Chart builders** for bar, grouped bar, time series, histogram and metric ([Q12](design/12-io-schema.md)).
  - **Citations** for every data point, with an exactness check on every response ([Q14](design/14-citations.md)).
  - `POST /v1/debug/plan`, which runs a hand-written plan through the whole non-AI pipeline.
- **Exit check:** appendix questions expressed as plans produce correct charts against recorded data. The tests caught three extraction bugs.
- **Live check:** per-status counts from fetching and grouping trials equal the API's own per-bucket counts exactly.

### M2: AI stages (first complete version)

- **Delivered:**
  - A model client on the OpenAI Responses API, with token usage, cost and a fallback model per stage ([Q20](design/20-model-selection.md)).
  - The **guard**, in parallel with planning, failing closed ([Q5b](design/05b-input-guard.md)).
  - The **planner agent**: a bounded LangGraph tool loop with `list_options`, `count_trials`, `check_plan` and `submit_plan` ([Q3](design/03-ai-vs-code.md)).
  - The **gate**: request fields override the plan, chart compatibility, entity grounding, and reasons for unrequested filters ([Q4b](design/04b-ai-validation.md)).
  - The **narrator**: a fact sheet with placeholders, checks for numbers, names, banned claims and length, one retry, then a template.
  - Error codes and bodies ([Q17](design/17-error-handling.md)), five example runs in [`docs/examples/`](examples/), and the first README.
- **Changed:** LangGraph runs only the planner's tool loop, where a graph helps. The request pipeline is plain async code, which is easier to follow and test.
- **Exit check:** the assignment's example request works, and every MUST requirement is met.
- **Live:** 7 of the 9 appendix questions pass end to end. The two network questions waited for M3. Live runs caught three narration problems, each fixed with a regression test first. Measured: about $0.003 of model cost per question.

### M3: Networks, scatter, series splits

- **Delivered:**
  - **Network graphs** ([Q13](design/13-networks.md)): drug co-occurrence, plus links between sponsors, drugs, conditions, collaborators, investigators and sites. Weights are distinct trials, edges carry Jaccard similarity, pruning is deterministic, communities are detected, and every node and edge is cited.
  - **Scatter plots**, one point per trial, with both values cited.
  - **Series splits** by a second dimension (e.g. trials per year by phase).
- **Changed:** the citations endpoint moved to M4, since it needs stored results. Live data showed that trial-level MeSH lists include non-drugs ("Specimen Handling"), so each drug now takes the MeSH term that shares a word with its name ([Q11](design/11-name-normalization.md) updated).
- **Exit check:** all 9 appendix questions pass end to end, including the two network questions. The melanoma drug network has 38 drugs and 129 links from 1,422 trials, built in 16 s.

### M4: Persistence, caches, jobs, cost

- **Delivered:**
  - Postgres tables through SQLAlchemy and Alembic ([Q16](design/16-database.md)): stored results, data points and citations, the plan cache, jobs, data versions and per-call model usage.
  - `GET /v1/results/{id}/citations`, which pages every trial behind a data point.
  - **Caches** that revalidate against daily data updates instead of expiring ([Q8](design/08-cache-ratelimit-retries.md)).
  - **Background jobs** for questions estimated above `SYNC_MAX_SECONDS`: 202 and polling, `SKIP LOCKED` workers, page progress, retries and restart recovery.
  - A daily model budget, `GET /v1/usage` behind an admin token, a per-client rate limit, and `GET /v1/options`.
- **Cut:** the page-level API cache (L1) and the `traces` table. Traces stay in logs and `meta`.
- **Exit check, live:** a repeated question is answered in 0.9 s instead of 13 s, with 1 model call instead of 4. A broad question becomes a job and completes with page progress.

### M5: Frontend

- **Delivered:** a Next.js app whose chart adapter reads field names **only from `encoding`**, tested against the real example responses. It has a citations panel with paging, method notes, a raw JSON view, job progress and shareable links. Compose gained a `web` service, so `make up` opens a working app.
- **Followed by** a full UI redesign: the evidence drawer, a validated colour-blind-safe palette, table views, themes with contrast gates in CI, and phone layouts.

### Between M5 and M6: correctness and speed

Live use surfaced problems that were fixed before deployment:

- **Counting what was asked.** A question about the number of sponsors per year was answered with a trial count. A new `distinct_count` measure counts sponsors, drugs and other entities (with an optional minimum number of trials). A new gate check rejects a plan that doesn't count what the question counts, and an unsupported measure gets a refusal with a suggestion instead of a substitute.
- **Speed.** Trials-per-year series use one count call per year instead of downloading every trial: 2010-2020 went from 412 s to 57 s, with identical numbers. Chart building moved off the event loop, so a large question no longer blocks other requests.
- **Less AI text.** The AI-written summary under each chart was removed as prone to hallucination and not required. The checked AI title stays ([Q4b revision](design/04b-ai-validation.md#revision-2026-10-24-the-ai-summary-is-removed)).
- **Local mirror revisited.** A local copy of the registry was reconsidered for broad questions and not built, because it would miss the API's synonym matching ([Q21](design/21-local-mirror-revisited.md)).

### M6: Deploy

- **Planned:** an EC2 instance defined in CloudFormation or CDK, with Caddy for HTTPS, and the frontend on Vercel.
- **Delivered:** Kubernetes (k3s) on one EC2 instance, defined in Terraform and Kustomize, with both the API and the web app on the cluster, Let's Encrypt certificates, and deploys through an SSM tunnel. The reasons for the change and a production design are in the [Q19 revision](design/19-deployment-ui.md#revision-2026-10-25-what-was-actually-deployed); how to deploy is in [`infra/README.md`](../infra/README.md).
- **Exit check:** the public endpoint answers the example request over HTTPS.
- **Followed by** documentation for API users: a hand-written API guide in the web app at `/docs`, and a complete OpenAPI reference behind Swagger and ReDoc.

## Cut lines

These were decided before the build, in the order they would be dropped if time ran short:

1. A demo video
2. The model bake-off beyond the planner
3. Network types beyond drug co-occurrence, sponsor - collaborator and condition - drug
4. The page-level API cache (L1) and the `traces` table
5. Frontend extras (field pickers, job progress)
6. Deployment

Line 4 was cut. The extra network types, the frontend extras and the deployment were all built. The bake-off is still planned (below).

Never cut: input validation, the plan gate, narration checks, citation exactness, honest handling of excluded trials and uninterpretable questions, and tests for the deterministic core.

## Risks and how they were handled

| Risk | Mitigation | Outcome |
|---|---|---|
| Planner quality below the bar | Tool feedback and a code gate first; a bigger model only as a last resort | All 9 appendix questions pass with the starting model (`gpt-5.4-mini`) |
| ClinicalTrials.gov throttling during development | Recorded fixtures for tests, a global client-side rate limiter, and the rate-limit test left for last | Measured on 2026-10-25 (~10 requests per 10 s); the limiter now allows 9 per 10 s ([live probe §8](api/live-probe.md)) |
| Broad questions too slow | Count per bucket before fetching, and background jobs, never a silent partial answer | Per-year counts became fast; broad questions that need every record still take minutes, as background jobs (see [limitations](../README.md#limitations)) |

## What's planned

- ~~An evaluation set for the AI stages and a model bake-off per stage.~~ **Done 2026-10-25** ([`docs/eval/`](eval/README.md), [Q20 results](design/20-model-selection.md#bake-off-results-2026-10-25)).
- **A live end-to-end set of about 60 questions** ([Q18](design/18-testing.md)), with a report of the results. Today's end-to-end suite has 11.
- ~~Remaining live checks against ClinicalTrials.gov (O4, O5).~~ **Done 2026-10-25** ([live probe §9-10](api/live-probe.md#9-statsfieldvalues-counting-and-the-250-value-cap-open-item-o4)).
- **Task-scoped authorization with [Tenuo](https://tenuo.ai/), once the agents can change things.** Today the planner's four tools only read (option lists, trial counts, plan checks), and the schemas, the validation gate and the step cap already limit them, so Tenuo would duplicate those checks. It becomes worth adding when:
  - the API is offered to other agents, for example as an MCP server: a signed warrant per task could limit which questions a caller may ask, how many ClinicalTrials.gov pages a question may fetch, and for how long;
  - tools gain side effects, such as saving, exporting or sending a chart: each call would be checked against the task's warrant before it runs, so a prompt injection can't widen what's allowed.

  Tenuo checks permissions, not correctness: the citation checks and count cross-checks stay as they are.
