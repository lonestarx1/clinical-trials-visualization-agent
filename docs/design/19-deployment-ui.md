# Design Q19: Deployment and demo UI

Status: **Decided** (2026-10-24)

## Frontend (Next.js, one codebase for local and deployed use)

| Feature | Detail |
|---|---|
| Input | Question box + **field pickers** built from `GET /v1/options` (drug, condition, sponsor, country, phase, status, years, compare groups, chart type override, sponsor role, match mode), plus example-question buttons |
| Charts | **Apache ECharts** for all 7 types (bar, grouped bar, time series, histogram, scatter, **network graph**, metric). One library, so a consistent look and a single renderer adapter from our spec |
| Citations | Click a bar / bucket / point / node / edge -> panel with the sampled citations (NCT ID link, title, field + exact excerpt) -> "view all" pages through `GET /v1/results/{id}/citations` |
| "How we got this" | Interpretation, assumptions, warnings, `excluded` counts, counting rule, applied filters, links to the exact ClinicalTrials.gov API queries, data timestamp, AI usage/cost |
| Background jobs | 202 -> progress bar polling `GET /v1/jobs/{id}` (stage, pages done/total) -> renders the result |
| Raw JSON | Toggle to show the exact response, so reviewers can inspect the structured output (the focus of the assignment) |
| Errors | Friendly messages per `error.code` / `status`, with the `trace_id` |
| Live / Fast (added 2026-10-25, [Q22](22-term-sets.md)) | A Live/Fast switch under the search box sends `mode`, with a line from `/health`'s `fast_mode` saying what fast mode does or why it is answering live now. The same switch beside an asked question re-asks it in the other mode. The choice is kept in shared links (`&mode=fast`), and each answer shows its source from `meta.data_source`: "Live from ClinicalTrials.gov" or "Fast: our copy of the <date> data, checked against ClinicalTrials.gov" |

The frontend is a **reference renderer**: it also proves that the response schema can be rendered "without guessing" (P3-12).

## Backend hosting: original plan (superseded)

> **Superseded on 2026-10-25.** This was the plan on 2026-10-24: Docker Compose on one EC2 instance behind Caddy, with the frontend on Vercel. It was not built. What runs today is described in [Revision (2026-10-25): what was actually deployed](#revision-2026-10-25-what-was-actually-deployed). The plan is kept so the reasoning in the revision's comparison table makes sense.

| Item | Decision |
|---|---|
| Compute | One small EC2 instance running the Docker Compose stack (`api` + `postgres`). The `web` service isn't needed there (frontend on Vercel). |
| HTTPS | **Caddy** reverse proxy with automatic Let's Encrypt certificates for **`api.engineeradriel.com`** |
| DNS | An `A` record `api.engineeradriel.com` -> the instance's Elastic IP, at the domain's DNS provider |
| Infrastructure as code | CloudFormation or AWS CDK stack: security group (80/443 only, SSH restricted or SSM Session Manager instead), EC2 instance + Elastic IP, IAM role for reading the secret, CloudWatch logs (optional) |
| Secrets | OpenAI key stored in **AWS Secrets Manager**, read at container start through the instance role. Never in the repo, the AMI, or a plain file on disk. |
| Public protection | Per-IP rate limit (our 429), daily LLM spending cap (`budget_exceeded`), CORS allows only the Vercel domain (+ localhost for dev), guard + all validation (Q5, Q5b) |
| Frontend | Vercel project from `frontend/`. Env var for the API base URL (`https://api.engineeradriel.com`), used by the Next.js server-side proxy |

## Configurable limits (open item O3)

Every protective limit **exists, is configurable via environment variables, and is documented in the README**. All of them are implemented as settings in [`backend/app/core/config.py`](../../backend/app/core/config.py). Defaults are deliberately **high**: the point is to show the controls are there, not to restrict realistic use. Operators can tighten them at any time.

| Limit | Env var | Default | Effect when hit |
|---|---|---|---|
| Per-client (IP) request rate | `RATE_LIMIT_PER_IP_PER_MIN` | 300 / min | 429 `too_many_requests` + `Retry-After` |
| Concurrent background jobs per client | `MAX_ACTIVE_JOBS_PER_IP` | 10 | 429 |
| Daily LLM spend | `LLM_DAILY_BUDGET_USD` | 100 | 503 `budget_exceeded` (cached results still served) |
| ClinicalTrials.gov request rate (global) | `CTGOV_RATE_LIMIT_PER_MIN` | 54 / min | Requests queue (not a client error); 10% under the measured limit (O6) |
| ClinicalTrials.gov burst | `CTGOV_RATE_BURST` | 9 | At most this many starts in any `burst * 60 / rate` s (10 s) |
| ClinicalTrials.gov concurrency | `CTGOV_MAX_CONCURRENCY` | 9 | Queueing |
| ClinicalTrials.gov count cache | `CTGOV_COUNT_CACHE_SECONDS` | 600 | Count calls repeat; 0 turns it off |
| Mirror sync ([Q22](22-term-sets.md)) | `MIRROR_SYNC_ENABLED` | false (on in the k3s deployment) | When on, the API process loads and updates the `registry` mirror |
| Mirror sync rate | `MIRROR_SYNC_RATE_PER_MIN` | 27 | The sync's cap, inside the shared ClinicalTrials.gov limiter: half the budget, so questions keep the rest |
| Fast mode ([Q22](22-term-sets.md)) | `FAST_MODE_ENABLED` | false (on in the k3s deployment) | Off: a `mode: "fast"` request is answered live, with a note |
| Fast mode: new term size | `FAST_NEW_TERM_MAX_TRIALS` | 20,000 | A term with no term set yet that matches more trials is answered live, rather than listed while the user waits |
| Fast mode: answer size | `FAST_MAX_TRIALS` | 300,000 | Larger questions are answered live (the records are read into memory either way) |
| Fast mode: shadow sample | `FAST_MODE_SHADOW_RATE` | 0.1 | Share of fast answers recomputed live in the background and compared; differences go to the log |
| Fast mode: shadow size | `FAST_MODE_SHADOW_MAX_PAGES` | 20 | Only fast answers of at most this many API pages are shadow-run, so shadows don't eat the API budget |
| Synchronous time budget (estimated duration) | `SYNC_MAX_SECONDS` | 60 s | Becomes a background job (a fast answer never does) |
| Stored result retention | `RESULT_TTL_HOURS` | 24 | 410 `expired` (Q16). Finished jobs keep a fixed 24 h |
| Planner step limit | `PLANNER_MAX_STEPS` | 6 | `could_not_interpret` |
| Citations inline (`full` mode) | `CITATIONS_FULL_MAX` | 2,000 | Falls back to sample mode |

## Revision (2026-10-25): what was actually deployed

| Item | Deployed |
|---|---|
| Where | **Kubernetes (k3s) on one EC2 t3.medium** in Seoul (ap-northeast-2), in a personal AWS account |
| Infrastructure as code | **Terraform** (S3 state with native locking) for the network, node, IAM, ECR, Secrets Manager and DNS; **Kustomize** manifests for the cluster (`infra/`) |
| App | Web app, API and Postgres all in the cluster. One Ingress (Traefik, built into k3s) serves both hosts. cert-manager provides Let's Encrypt certificates, and HTTP redirects to HTTPS |
| URLs | **https://trials.cheiron.engineeradriel.com** (web) and **https://api.cheiron.engineeradriel.com** (API), two A records in the existing Route 53 zone |
| Access | No SSH and no public Kubernetes API. Admin access and deploys go through SSM Session Manager (`make deploy` opens a port-forwarding tunnel only while it runs) |
| Secrets | OpenAI key in Secrets Manager (value set outside Terraform). Postgres password generated on the node. A timer syncs both, plus the ECR pull token, into Kubernetes Secrets |
| Memory | 4 GB node + 8 GB swap file. The kubelet runs with `LimitedSwap`, because Kubernetes keeps pods off swap by default. The largest question peaks at about 2 GB in the API |
| Cost | About **$1.50/day**; `make infra-destroy` removes everything |

Details: [`infra/README.md`](../../infra/README.md).

### Why this setup (time and cost)

The deployment had two hard constraints: the **submission deadline** (15:00 KST the same day) and **cost**, since it's paid personally and runs for a few days. Within those, we wanted the deployment to **show Kubernetes**.

| Option | Per day | Why not chosen |
|---|---|---|
| EC2 + Docker Compose + Caddy, CDK ([the original plan above](#backend-hosting-original-plan-superseded)) | ~$1.50 | Cheapest and simplest, but shows no orchestration |
| Frontend on Vercel + API on EC2 | ~$1.50 | Two platforms, CORS and two sets of settings, for a demo that runs a few days. Dropped to keep one deployment path |
| Amazon ECS on one EC2 | ~$2 | Shows AWS's own orchestrator, not Kubernetes |
| Amazon EKS, 1 node + ALB | ~$4.70 | Managed Kubernetes, but the $2.40/day control plane alone costs more than the whole k3s node, and it takes more setup time before the deadline |
| EKS, cut down (spot node, ingress-nginx instead of ALB) | ~$2.70 | Still pays for the control plane; spot can interrupt a demo |
| EKS deployed once, then switch to one EC2 | n/a | Builds two deployment paths before the deadline, and one gets thrown away |
| **k3s on one EC2 (chosen)** | **~$1.50** | Real, CNCF-certified Kubernetes: the same manifests, kubectl and Helm as EKS, without the control-plane fee |

**Trade-offs we accept for the demo:**
- one node, so no high availability;
- no CDN in front of the web app;
- Postgres in the cluster on the node's disk, which is acceptable because it only holds caches, stored answers and the job queue, all of which can be rebuilt.

The portability is shown, not just claimed: `infra/k8s/overlays/eks` runs the same base on EKS.

**Node size.** A t3.small (2 GB) was considered, to save about $0.60/day. It was rejected: k3s, Postgres and the web app already use about 1.2 GB, so the largest question would run almost entirely from swap.

## Production path (how we'd run it for real users)

The same container images and the same Kustomize base; what changes is everything around them.

| Area | Production design |
|---|---|
| **Cluster** | **Amazon EKS**, nodes in private subnets across **3 Availability Zones**. Managed node groups: on-demand for the API, spot for background workers |
| **Database** | **Amazon RDS for PostgreSQL**, Multi-AZ, automated backups and point-in-time recovery; replaces the in-cluster StatefulSet |
| **Workers** | Background jobs move out of the API process into a separate **worker Deployment**, scaled on queue depth (KEDA reading the `jobs` table). The `SKIP LOCKED` queue and heartbeats already support this |
| **Shared rate limiter** | ClinicalTrials.gov limits requests per IP. All pods leave through the **NAT gateways' IPs**, and one limiter, shared in **Redis (ElastiCache)** or a Postgres token bucket, keeps the whole fleet under the limit. Redis also takes the hot cache (Q15) |
| **Edge** | **CloudFront** in front of the web app (CDN for static assets; Next.js on the cluster or a managed host) and the API. **ALB** through the AWS Load Balancer Controller, with **ACM** certificates and **AWS WAF** (rate rules, managed rule sets) |
| **Secrets** | **External Secrets Operator** syncing Secrets Manager into Kubernetes, scoped per service with IRSA / EKS Pod Identity |
| **Delivery** | GitHub Actions with **OIDC to AWS** (no stored keys): test → build → scan → push to ECR. **Argo CD** (GitOps) rolls out from a deploy repo or overlay. Separate **staging and production** environments from the same Terraform modules |
| **Reliability** | API replicas ≥ 2 across zones, HPA on CPU and latency, PodDisruptionBudgets, readiness gates, and a rollback path that re-points Argo CD to the previous image tag |
| **Observability** | Structured JSON logs (already emitted) to CloudWatch or Loki; metrics in Prometheus/Grafana (latency, job queue depth, ClinicalTrials.gov 429s, LLM spend); OpenTelemetry traces keyed by the existing `trace_id`; alerts on errors, queue age and budget |
| **Security** | NetworkPolicies (only the API reaches Postgres), images signed and scanned, non-root containers (already), least-privilege IAM per workload, audit logs |
| **Cost control** | Spot for workers, Savings Plans for the steady base, budget alerts, and the existing daily LLM spend cap |

## Submission

- **Zip of the repository** (Part 6), runnable with `docker compose up` / `make up` (Q15).
- **Deployed endpoints:** `https://api.cheiron.engineeradriel.com` (API) and `https://trials.cheiron.engineeradriel.com` (web app); see the revision above.
- Optional short demo video.

## Requirement links

P3-13, P6-7, P6-8, P6-9 (UI, deployed endpoint, demo video bonuses), P1-6, P3-12 (renderable without guessing), P6-2 (how to run).
