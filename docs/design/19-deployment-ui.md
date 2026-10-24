# Design Q19: Deployment and Demo UI

Status: **Decided** (2026-10-24, with the user)

## Frontend (Next.js, one codebase for Docker Compose and Vercel)

| Feature | Detail |
|---|---|
| Input | Question box + **field pickers** built from `GET /v1/options` (drug, condition, sponsor, country, phase, status, years, compare groups, chart type override, sponsor role, match mode), plus example-question buttons |
| Charts | **Apache ECharts** for all 7 types (bar, grouped bar, time series, histogram, scatter, **network graph**, metric). One library, so a consistent look and a single renderer adapter from our spec |
| Citations | Click a bar / bucket / point / node / edge -> panel with the sampled citations (NCT ID link, title, field + exact excerpt) -> "view all" pages through `GET /v1/results/{id}/citations` |
| "How we got this" | Interpretation, assumptions, warnings, `excluded` counts, counting rule, applied filters, links to the exact ClinicalTrials.gov API queries, data timestamp, AI usage/cost |
| Background jobs | 202 -> progress bar polling `GET /v1/jobs/{id}` (stage, pages done/total) -> renders the result |
| Raw JSON | Toggle to show the exact response, so reviewers can inspect the structured output (the focus of the assignment) |
| Errors | Friendly messages per `error.code` / `status`, with the `trace_id` |

The frontend is a **reference renderer**: it also proves that the response schema can be rendered "without guessing" (P3-12).

## Backend hosting (AWS)

| Item | Decision |
|---|---|
| Compute | One small EC2 instance running the Docker Compose stack (`api` + `postgres`). The `web` service isn't needed there (frontend on Vercel). |
| HTTPS | **Caddy** reverse proxy with automatic Let's Encrypt certificates for **`api.engineeradriel.com`** |
| DNS | An `A` record `api.engineeradriel.com` -> the instance's Elastic IP, added in the user's DNS provider (the user confirms the provider/record before it's created) |
| Infrastructure as code | CloudFormation or AWS CDK stack (per the user's AWS guidelines): security group (80/443 only, SSH restricted or SSM Session Manager instead), EC2 instance + Elastic IP, IAM role for reading the secret, CloudWatch logs (optional) |
| Secrets | OpenAI key stored in **AWS Secrets Manager**, read at container start through the instance role. Never in the repo, the AMI, or a plain file on disk. |
| Public protection | Per-IP rate limit (our 429), daily LLM spending cap (`budget_exceeded`), CORS allows only the Vercel domain (+ localhost for dev), guard + all validation (Q5, Q5b) |
| Frontend | Vercel project from `frontend/`. Env var for the API base URL (`https://api.engineeradriel.com`), used by the Next.js server-side proxy |

## Configurable limits (decided with the user, O3)

Every protective limit **exists, is configurable via environment variables, and is documented in the README**. Defaults are deliberately **high**: the point is to show the controls are there, not to restrict realistic use. Operators can tighten them at any time.

| Limit | Env var | Default | Effect when hit |
|---|---|---|---|
| Per-client (IP) request rate | `RATE_LIMIT_PER_IP_PER_MIN` | 300 / min | 429 `too_many_requests` + `Retry-After` |
| Concurrent background jobs per client | `MAX_ACTIVE_JOBS_PER_IP` | 10 | 429 |
| Daily LLM spend | `LLM_DAILY_BUDGET_USD` | 100 | 503 `budget_exceeded` (cached results still served) |
| ClinicalTrials.gov request rate (global) | `CTGOV_RATE_LIMIT_PER_MIN` | 40 / min | Requests queue (not a client error); this one protects us from being blocked, so it stays conservative until O6 is measured |
| ClinicalTrials.gov concurrency | `CTGOV_MAX_CONCURRENCY` | 2 | Queueing |
| Synchronous time budget (estimated duration) | `SYNC_MAX_SECONDS` | 60 s | Becomes a background job |
| Planner step limit | `PLANNER_MAX_STEPS` | 6 | `could_not_interpret` |
| Citations inline (`full` mode) | `CITATIONS_FULL_MAX` | 2,000 | Falls back to sample mode |

## Production path (documented, not built)

Container orchestration (Amazon ECS on Fargate or Kubernetes on Amazon EKS), Terraform/CDK for all infrastructure, Amazon RDS for Postgres, separate worker service, Redis for the shared rate limiter / queue / hot cache (Q15), WAF, centralised logs/metrics/traces, autoscaling, and CI/CD deploys.

## Submission

- **Zip of the repository** (Part 6), runnable with `docker compose up` / `make up` (Q15).
- **Deployed endpoint:** `https://api.engineeradriel.com` (+ the Vercel frontend URL).
- Optional short demo video.

## Requirement links

P3-13, P6-7, P6-8, P6-9 (UI, deployed endpoint, demo video bonuses), P1-6, P3-12 (renderable without guessing), P6-2 (how to run).
