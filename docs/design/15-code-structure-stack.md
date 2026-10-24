# Design Q15: Code Structure, Stack, Agent Framework, Packaging

Status: **Decided** (2026-10-24)

## Stack

| Concern | Choice |
|---|---|
| Language / runtime | Python 3.12 |
| Web framework | FastAPI (OpenAPI docs generated automatically) |
| Data models / validation | Pydantic v2 (request, response, plan, registry) |
| Configuration | Pydantic Settings: typed, validated at startup, from env vars / `.env` (incl. per-stage model settings, Q20) |
| HTTP client | `httpx` (async) |
| Database | Postgres (cache, jobs, results, traces) via SQLAlchemy 2 (async) + Alembic migrations |
| **Agent framework** | **LangGraph** (see below) |
| LLM provider | OpenAI (key provided by Cheiron; models configurable) |
| Packaging / deps | `uv` |
| Concurrency | **async I/O (asyncio)**; CPU-heavy steps optionally in a worker pool |

## Concurrency: async I/O, not multithreading

Nearly all request time is **waiting on the network** (OpenAI calls, ClinicalTrials.gov, Postgres). With asyncio, one process overlaps that waiting:
- the guard runs alongside the planner (Q5b)
- parallel slice fetching (Q6)
- concurrent requests and background jobs

Python threads would add locking complexity without benefit for I/O-bound work. CPU-bound steps (normalising/aggregating ~17k trials, community detection on networks) can be moved to a process/thread pool executor if profiling shows they block the event loop.

## Agent framework: LangGraph

Compared (2026-10-24):

| Framework | Strength | Fit |
|---|---|---|
| **LangGraph** | Widely described as the most used agent framework in production; workflows as directed graphs with explicit state, branching and retries | **Chosen.** Pipeline stages, conditional retries and the planner's tool loop map directly onto graph nodes and edges. |
| OpenAI Agents SDK | Lightweight; built-in guardrails, handoffs, tracing | Strong match for the guard pattern, but ties the agent layer to one vendor |
| PydanticAI | Typed, minimal, structured outputs with validators | Good fit for strict schemas; less widely recognised |
| CrewAI / AutoGen | Multi-agent collaboration | Overkill for one bounded planner; AutoGen reportedly moved to maintenance mode |

Sources: JetBrains PyCharm blog (2026-06), Fungies, Next-IT, Uvik comparisons. Popularity figures in those posts could not be verified against primary sources.

**How we use it:**
- The request pipeline is a LangGraph **state graph**: input validation -> (guard ∥ planner) -> plan gate -> retrieve -> normalize -> aggregate -> build chart -> narrate -> narration checks -> verify -> respond.
- Conditional edges handle repair/retry and fallbacks.
- The **planner** is a bounded tool-calling sub-agent (`list_options`, `check_plan`, `count_trials`, `submit_plan`) with a step limit.
- Non-AI stages are plain, deterministic Python functions called from nodes, so they stay unit-testable without the framework.

## Code structure

```
app/
  api/          routes: query, jobs, results/citations, options, health
  schemas/      request, response, plan (Pydantic)
  registry/     dimensions, measures, chart types, network types (declarative)
  agents/       guard, planner (+ tools), narrator, prompts, LangGraph graph
  validation/   plan gate, fact sheet, narration checks, citation check
  ctgov/        API client (rate limiter, retries, cache), query AST -> Essie, fetch strategies
  pipeline/     normalize -> aggregate -> chart builders -> orchestration helpers
  store/        Postgres models: cache, jobs, results, traces (+ Alembic migrations)
  workers/      background job runner
  core/         config, logging, tracing
tests/          unit · contract · integration (recorded API fixtures) · AI eval
```

**Extension principle:** a dimension is **one registry entry** (kind, API fields, extractor, counting rule, order, filter compiler, citation field path). The planner's options, validation, field selection, aggregation and citations all read from the registry. A new dimension = one entry + one test. Chart builders are one class per chart type, registered by name.

## Packaging and deployment

| Target | Setup |
|---|---|
| **Submission (reproducible locally)** | **Docker Compose**: `api` container (FastAPI + in-process background workers) + `postgres` container. One command to run. |
| **Live demo** | **Superseded (2026-10-25).** Originally: the same Compose stack on an AWS EC2 instance behind an HTTPS reverse proxy (e.g. Caddy), with the Next.js frontend on Vercel. What runs today: web app, API and Postgres on k3s (Kubernetes) on one EC2 instance, both hosts served over HTTPS by one Ingress. See [Q19, what was actually deployed](19-deployment-ui.md#revision-2026-10-25-what-was-actually-deployed). |
| **Production (documented, not built)** | Container orchestration (Amazon ECS on Fargate, or Kubernetes on Amazon EKS), infrastructure as code (Terraform), managed Postgres (Amazon RDS), separate worker service, secrets in a secrets manager, centralised logs/metrics/traces. Refined in [Q19's production path](19-deployment-ui.md#production-path-how-wed-run-it-for-real-users) (EKS). |

### One-command local demo (frontend included)

The Compose stack includes the frontend, so reviewers can use the system right away:

| Service | Role | Starts after |
|---|---|---|
| `postgres` | Database | (healthcheck: `pg_isready`) |
| `api` | FastAPI + background workers; runs Alembic migrations on start | `postgres` healthy (healthcheck: `/health`) |
| `web` | Next.js app (production build, standalone output) | `api` healthy |

- **Repo layout:** `backend/` + `frontend/` in one repository. The same `frontend/` code runs in Compose and in the deployed cluster.
- **Same-origin calls:** the Next.js app forwards `/api/*` to the `api` container (server-side), so the browser talks to one address. No CORS issues locally, and the API URL is a **runtime** setting (not baked into the build). (The original plan pointed the same setting at the EC2 API from Vercel; superseded, see Q19.)
- **One `.env`:** only `OPENAI_API_KEY` is required; everything else has defaults.
- **Opening the browser:** a container **can't** open the host's browser. So:
  - (a) `docker compose up` logs a clear "Open http://localhost:3000" line, and the README says the same.
  - (b) An optional `make up` / `./run.sh` runs Compose, waits for all healthchecks, then opens the browser (`open` on macOS, `xdg-open` on Linux).
- Reviewer flow: `cp .env.example .env` -> paste key -> `make up` -> the browser opens on a working app.

Docker Compose is chosen so reviewers can reproduce the whole system locally. It isn't a claim that Compose is the right production platform.

## Redis: not in the submission, part of the production path

Considered twice (Q8 for caching, here for infrastructure). **Not included** in the Compose stack:

- We run **one instance**, so an in-process rate limiter is correct.
- Postgres handles a simple job queue (`SELECT ... FOR UPDATE SKIP LOCKED`).
- The cache is not the bottleneck (Q8).

Adding Redis now would be one more service to run and explain, for no measurable gain.

**In production, Redis would earn its place in three ways:**

1. **Shared rate limiter** across multiple API instances. This is the strongest reason: the ClinicalTrials.gov budget is per IP/client, and an in-process limiter breaks as soon as there are two instances.
2. **Job queue** for a separate worker service (e.g. arq/RQ/Celery), with pub/sub for job progress.
3. **Hot cache** in front of Postgres at high read volumes.

## Requirement links

P6-1, P6-2 (all code, how to run), P6-8 (deployed endpoint), P7-2 (maintainable structure, extensibility), P7-6 (planning steps + tools), P7-7 (organisation).
