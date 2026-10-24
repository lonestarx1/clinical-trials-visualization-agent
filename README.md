# ClinicalTrials.gov Query-to-Visualization Agent

A backend service that turns a natural-language question about clinical trials into a structured, frontend-ready **visualization spec**, computed from live [ClinicalTrials.gov API](https://clinicaltrials.gov/data-api/api) data, with **citations for every data point** (NCT ID + the exact field and value it came from).

```
POST /v1/query  {"query": "How are breast cancer trials distributed across phases?"}
-> 200 {"status": "ok", "visualization": {"type": "bar_chart", "title": ..., "encoding": ..., "data": [...]}, "meta": {...}}
```

**Live:** web app at **https://trials.cheiron.engineeradriel.com**, API at **https://api.cheiron.engineeradriel.com** ([interactive reference](https://api.cheiron.engineeradriel.com/docs)).

> **Status:** milestones M0-M6 done.
> - **Pipeline:** question → validated plan → live data → chart spec, with citations and an AI-written, checked title.
> - **Charts:** 7 types, including **network graphs**.
> - **Measures:** trial counts, enrollment, and **distinct sponsors, drugs, countries and more, with an optional minimum number of trials**.
> - **Honesty:** the AI can't swap in a different measure. A question asking for something we can't compute gets a clear refusal and a suggestion.
> - **Storage:** stored results with **full citation lists**, and plan and result caches with revalidation.
> - **Speed:** background jobs for broad questions, and per-year counts without downloading.
> - **Cost:** AI cost tracking with a daily cap.
> - **Results:** **all 9 appendix questions pass end to end**.
> - **Deployed** on Kubernetes (k3s) with Terraform.
>
> Next: evaluation (M7). See [the implementation plan](docs/implementation-plan.md).

## Quick start

Requirements: Docker with Compose v2.

```bash
cp .env.example .env    # then set OPENAI_API_KEY
make up                 # builds and starts postgres + api + web, waits until healthy, opens http://localhost:3000
curl -s localhost:8000/v1/query -H 'Content-Type: application/json' \
  -d '{"query": "Which countries have the most recruiting trials for lung cancer?"}'
```

- Web UI: http://localhost:3000 (questions can be shared as `?q=...` links)
- Interactive API docs (OpenAPI): http://localhost:8000/docs

![An answer: the question stays at the top, the chart below it, every bar traceable to its trials](docs/screenshots/answer.png)

## Web UI

A Next.js + Apache ECharts app in [`frontend/`](frontend/), built for people who need to trust the numbers:

- **Ask in plain words**, or refine with filters (drug, condition, sponsor, country, phase, status, years, chart type) shown as removable chips. Grouped example questions and your recent questions on the home screen.
- **The question stays with its answer.** On submit, the search box glides up and becomes the page's heading, in your own words. Click it or press `/` to edit it in place, and `Esc` to cancel.
- **Every chart traces back to the trials.** Click any bar, point, node or link: a drawer lists the trials behind it, each with the exact record lines that put it there, highlighted (field path on hover), and pages through all of them.
- **Readable charts:** a colour-blind-safe palette validated for light and dark surfaces, horizontal bars for names, direct value labels, networks with clusters named after their largest entity, and a **table view** of every value.
- **Plain-language method notes:** what was counted, how the question was read, what was not counted, and links to the exact ClinicalTrials.gov queries. Technical details and the raw JSON fold away.
- **10 colour themes** (5 light, 5 dark, including high contrast) plus "Automatic"; Clinical light is the default. Every theme passes contrast checks in CI (text ≥ 12:1, secondary text ≥ 7:1).
- **Smooth to use:** progress while answers are computed (real page progress for background jobs), shareable links to an answer (`?q=`) and to one data point's trials (`&d=`), PNG download, keyboard and screen-reader support, phone layouts.

The charts are drawn **only from the response's `encoding`** ([`lib/adapter.ts`](frontend/lib/adapter.ts), tested against the example JSONs), which shows the schema renders without guessing. The app proxies `/api/*` to the backend, so the API address is a runtime setting (`API_BASE_URL`).

| Home | Evidence for one bar | Drug network |
|---|---|---|
| ![Home screen with example questions](docs/screenshots/home.png) | ![Evidence drawer: the trials behind "China", with the matching record line highlighted](docs/screenshots/evidence.png) | ![Melanoma drug co-occurrence network with named clusters](docs/screenshots/network.png) |

| Theme picker | Midnight theme | Phone |
|---|---|---|
| ![The theme dropdown with 10 themes](docs/screenshots/themes.png) | ![An answer in the Midnight dark theme](docs/screenshots/dark.png) | ![An answer on a phone](docs/screenshots/phone.png) |

## How it works

```
request ─► validate (422) ─┬─► guard (AI, fail closed) ──────────────┐
                           └─► planner agent (AI + code tools) ──► gate (code) ─► compile ─► retrieve ─► aggregate ─► chart ─► verify citations ─► narrate (AI) ─► response
```

| Stage | Who | What |
|---|---|---|
| Guard | AI (`gpt-5.4-nano`) | Flags clearly malicious requests (prompt injection, misuse). Runs in parallel with planning. If it can't answer, the request is refused (503): **fail closed**. |
| Planner | AI agent (`gpt-5.4-mini`, LangGraph) | Turns words into **choices from fixed lists**: intent, chart type, dimension, measure, filters, comparison groups. Tools: `list_options`, `count_trials` (a real API count), `check_plan`, `submit_plan`. Bounded to 6 steps. |
| Gate | Code | Re-checks every plan: schema, chart compatibility, **entity grounding** (every drug/condition/sponsor must come from the user's words), unrequested filters need a stated reason, and **the plan must count what the question counts** ("how many sponsors" can't become a trial count). Structured request fields override the AI. |
| Compile, retrieve | Code | Plan -> Essie query tree (user text can only ever be a quoted phrase) -> ClinicalTrials.gov, with a global rate limiter, retries and a circuit breaker. Trials-per-year series are **counted with one call per year** instead of downloading every trial (2010-2020: 412 s → 57 s). |
| Aggregate, chart | Code | Every number. Measures: trials, total or median enrollment, and **distinct entities** (e.g. lead sponsors with at least 3 trials per year). Explicit counting rules for multi-valued fields, nothing silently dropped (`meta.excluded`). Runs off the event loop, so a large question doesn't stall other requests. |
| Verify | Code | Every citation excerpt is compared with the record it came from; a mismatch fails the request. |
| Narrate | AI (`gpt-5.4-nano`) | Writes the chart title **with placeholders** filled from a fact sheet, so numbers are correct by construction. Checked for invented numbers, names not in the chart, evaluative claims, length and repeated phrases; one retry, then a template title. No free-text summary: it was removed as hallucination-prone and not required ([decision](docs/design/04b-ai-validation.md#revision-2026-10-24-the-ai-summary-is-removed)). |

Networks: one entity dimension gives co-occurrence (drugs used together), two give links between kinds (sponsor - drug, condition - drug, sponsor - collaborator, investigator - site). Node and edge weights are distinct trials, edges also carry Jaccard similarity, the graph is pruned deterministically (recorded in `meta.network`), and communities are detected: in the melanoma example they separate lymphodepletion + IL-2 regimens, chemotherapy, checkpoint + BRAF/MEK therapy and peptide vaccines.

The AI never produces a number or a citation. Models are configurable per stage (`GUARD_MODEL`, `PLANNER_MODEL`, `NARRATOR_MODEL`, each with a fallback model).

## API

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/query` | Question -> chart spec (200), or a background job for broad questions (**202** + `poll_url`) |
| `GET` | `/v1/jobs/{job_id}` | Job status, page progress, and the result when done (kept 24 h after finishing, then `410 expired`) |
| `GET` | `/v1/results/{result_id}/citations?datum=<key>&cursor=&page_size=` | **Every** trial behind one data point (bar, bucket, node, edge...), keyset-paginated |
| `GET` | `/v1/options` | Dimensions, measures, chart types and filter values with labels (for pickers) |
| `GET` | `/v1/usage` | Today's LLM calls and cost (admin token) |
| `GET` | `/health` | Database + ClinicalTrials.gov status and data timestamp |

### `POST /v1/query`

| Field | Type | Required | Notes |
|---|---|---|---|
| `query` | string | yes | 1-1,000 characters |
| `drug_name`, `condition`, `sponsor`, `country` | string or string[] | no | OR within a field; up to 10 terms of up to 200 characters. **Override the question.** |
| `trial_phase` | string[] | no | `PHASE1`... or labels like `"Phase 3"` |
| `status` | string[] | no | Overall status, e.g. `RECRUITING` or `"Recruiting"` |
| `start_year`, `end_year` | int | no | Start-date range |
| `compare` | 2-4 x `{label, drug_name?, condition?, sponsor?, country?}` | no | Comparison groups |
| `chart_type` | enum | no | `bar_chart`, `grouped_bar_chart`, `time_series`, `histogram`, `scatter_plot`, `network_graph`, `metric`. Checked against the plan: one that can't show the question answers 200 `could_not_interpret` (not 422: fit depends on the dimension the planner picks) |
| `top_n` | int 1-50 | no | |
| `match_mode` | `strict` \| `broad` | no | Drug/condition matching (default `strict`) |
| `sponsor_role` | `lead` \| `any` | no | Default `lead` |
| `citations` | `sample` \| `full` | no | Default `sample`. `full` inlines every citation, up to 2,000 per response (`CITATIONS_FULL_MAX`); above that it falls back to a sample and `meta.citations.reason` says why |
| `citations_per_datum` | int 1-50 | no | Default 5 |
| `phase_mode`, `condition_source`, `include_unknown`, `edge_metric`, `hide_query_entity` | | no | See [request fields](docs/design/05-request-fields.md) |

Unknown fields are rejected (422). Full schema: `/openapi.json`.

### Response

```jsonc
{
  "schema_version": "2.0",
  "status": "ok",                       // or no_matching_trials | out_of_scope | could_not_interpret (200, visualization null)
  "visualization": {
    "type": "bar_chart",
    "title": "...",
    "encoding": {                       // every data key is named here: no guessing
      "x": {"field": "phase", "type": "ordinal", "label": "Phase", "sort": "natural"},
      "y": {"field": "trial_count", "type": "quantitative", "label": "Number of trials", "unit": "trials"}
    },
    "data": [
      {"key": "PHASE2", "phase": "Phase 2", "trial_count": 3546, "citation_count": 3546, "citations_truncated": true,
       "citations": [{"nct_id": "NCT...", "url": "https://clinicaltrials.gov/study/NCT...", "title": "...",
                      "evidence": [{"field": "protocolSection.designModule.phases[0]", "excerpt": "PHASE2"}]}]}
    ]
  },
  "meta": {
    "interpretation": {...}, "filters": {...}, "assumptions": [...], "warnings": [...], "notes": [...],
    "counting_rule": "...", "additive": true, "unique_trials": 16765, "excluded": [{"reason": "no start date", "count": 5}],
    "api_queries": [{"group": null, "url": "https://clinicaltrials.gov/api/v2/studies?...", "total_count": 16765}],
    "data_timestamp": "...", "guard": {...}, "planner": {...}, "narration": {...},
    "usage": {"llm_calls": 4, "cost_usd": 0.0027}, "timings_ms": {...}, "trace_id": "..."
  }
}
```

Per chart type: [response schema design](docs/design/12-io-schema.md). Each data point carries up to `citations_per_datum` citations inline (all of them with `citations: "full"`) plus `citation_count`; the full list always comes from the citations endpoint using the response's `result_id` and the data point's `key`. `meta.citations` reports the mode `requested` and `applied`, and the `reason` when they differ. `meta.cache` says whether the plan and result came from cache (`hit`, `revalidated`, `miss`).

Errors share one body, routing errors included: `{"error": {"code", "message", "details", "trace_id"}}` with codes `invalid_request` (422), `rejected_by_policy` (400), `unauthorized` (401, `/v1/usage`), `not_found` (404, also unknown paths), `method_not_allowed` (405), `expired` (410, results and jobs), `too_many_requests` (429), `upstream_unavailable` / `llm_unavailable` / `safety_check_unavailable` / `budget_exceeded` (503) and `internal_error` (500). Once the daily AI budget is spent, `budget_exceeded` goes only to questions that need a model call: an exact repeat whose stored answer is still valid is answered with no model call.

## Examples (real outputs)

Generated by [`scripts/run_examples.py`](scripts/run_examples.py) against the running stack on 2026-10-24 with live data; never edited by hand. When schema 2.0 removed `visualization.summary`, a script dropped that key from them and set `schema_version` to `"2.0"`; nothing else changed.

| # | Request | Chart | Trials | Time |
|---|---|---|---|---|
| 1 | "How has the number of trials for this drug changed per year since 2015?" + `drug_name: Pembrolizumab` (the assignment's example) | [time_series](docs/examples/1-drug-trend.json) | 2,586 | ~10 s |
| 2 | "How are breast cancer trials distributed across phases?" | [bar_chart](docs/examples/2-condition-phases.json) | 16,765 | ~32 s |
| 3 | "Compare phases for trials involving pembrolizumab vs nivolumab." | [grouped_bar_chart](docs/examples/3-drug-comparison.json) | 4,228 | ~16 s |
| 4 | "Which countries have the most recruiting trials for lung cancer?" | [bar_chart](docs/examples/4-recruiting-countries.json) | 2,182 | ~11 s |
| 5 | "Which drugs frequently co-occur in combination studies for melanoma?" | [network_graph](docs/examples/5-drug-network.json) | 1,422 | ~16 s |

AI cost per question: about $0.003 (measured, `meta.usage`).

## Key design decisions

The full reasoning, alternatives and requirement links are in [docs/design](docs/design/README.md) (21 decisions). The main ones:

- **AI chooses, code computes.** The planner picks from registry lists; all numbers and citations come from deterministic code. The AI writes only the chart title, with placeholders; there is no free-text summary.
- **Live API, exact answers.** Every chart is computed from ClinicalTrials.gov at request time, never sampled. A local mirror was designed twice and not built. The deciding reason is accuracy: the API resolves drug and condition synonyms, and a plain local match misses about 20% of "lung cancer" trials ([Q21](docs/design/21-local-mirror-revisited.md)).
- **Refuse rather than substitute.** If no measure computes what was asked (e.g. an average duration), the answer says so and suggests the closest question that can be answered, instead of quietly charting something else.
- **Strict matching by default.** Drugs match intervention names (with the API's own synonym expansion: "Keytruda" finds pembrolizumab trials); conditions are quoted phrases; "sponsor" means lead sponsor. `match_mode` / `sponsor_role` widen it. Measured in the [live probe](docs/api/live-probe.md).
- **Explicit counting rules.** 17% of trials have two phases, and trials list many drugs, conditions and countries. Every chart states its rule, whether bars add up (`meta.additive`) and how many distinct trials it covers.
- **Defence in depth.** Request validation, an AI guard, a strict plan schema, entity grounding, and an expression tree that makes query injection impossible. Verified live: an injection attempt matched under 100 trials, not all ~600k.
- **Caching that stays correct.** Repeated questions reuse the stored plan (no planner call) and the stored answer. ClinicalTrials.gov refreshes daily, so a stored answer is reused only if the data version is unchanged, or after revalidation: no matching trial updated since, and the same total (2 cheap counts instead of refetching). Measured: a repeat question in 0.9 s instead of 13 s, with 1 model call instead of 4.
- **Background jobs** for questions estimated above `SYNC_MAX_SECONDS` (60 s): 202 + polling with page progress, one active job per identical request, `SKIP LOCKED` workers, retries, restart recovery.
- **One registry.** A dimension is one entry (API fields, filter, enum, counting rule); options, validation, retrieval, aggregation and citations all read from it.

## Testing and validation

Written test-first (each `test:` commit fails before the `feat:` commit that follows it).

| Suite | Command | What |
|---|---|---|
| Offline (CI) | `make test` | 407 unit, contract and integration tests: compiler strings written by hand, chart numbers worked out by hand from recorded real trials and small fixtures, scripted fake models for the agents |
| Database | `make test-db` | 23 tests against Postgres (its own `ctviz_test` database): repositories, stored results and citation paging, plan and result caches (per citation mode), background jobs (heartbeats, requeue after a restart, expiry), the daily budget (cached answers still served) |
| Live API | `make test-live` | 18 checks: query syntax against the real API, and **cross-checks**. Our aggregated counts equal the API's own counts exactly, and the sponsor counts and per-year counts equal an independent tally of the raw records |
| End to end | `make test-e2e` | 11 questions through the running stack, real models and live data: **the 9 appendix questions all pass**, plus a sponsor-count question and a refused "average duration" |
| Web | `make test-web` | 57 tests: the chart adapter against the example responses, theme contrast gates, the question and evidence helpers |

## Limitations (current)

- Very broad questions that need per-trial data (e.g. sponsors per year across 273k trials) still take minutes, as background jobs. Plain trials-per-year counts are fast (one call per year). A local mirror would make the rest instant, but can't match the API's synonym search yet ([Q21](docs/design/21-local-mirror-revisited.md)).
- Shares and percentages are not a measure: "what share of trials have results, by phase" shows counts with and without results side by side, not a percentage.
- Not built from the database design: the page-level API cache (L1) and the `traces` table (traces live in logs and `meta`).
- Sponsor names are not merged across spellings ("Merck Sharp & Dohme LLC" vs "Merck & Co."). MeSH grouping inherits MeSH quirks: "aldesleukin" and "Interleukin-2" can be separate drug nodes.
- The ClinicalTrials.gov rate limiter, the per-client limit and the job workers are in-process (one instance); several instances would need a shared store such as Redis.

## Deployment

Live at **https://trials.cheiron.engineeradriel.com** (web app) and **https://api.cheiron.engineeradriel.com** (API).

It runs on **Kubernetes (k3s) on one EC2 t3.medium**, defined in **Terraform** (network, node, IAM, ECR, Secrets Manager, DNS) and **Kustomize** (Postgres, API, web, Ingress with Let's Encrypt). `make deploy` builds, pushes and rolls out through an SSM tunnel: there's no SSH and no public Kubernetes API.

**Why this setup:** the submission deadline and cost (about $1.50/day). k3s is real Kubernetes, with the same manifests and Helm as EKS, but without EKS's $2.40/day control-plane fee. The same base also has an EKS overlay.

**In production** it would run on EKS across three zones, with:
- RDS for Postgres;
- background workers scaled on queue depth;
- one rate limiter shared by all pods (ClinicalTrials.gov limits per IP);
- CloudFront, WAF and an ALB in front;
- External Secrets, and GitOps deploys with Argo CD.

The reasons and alternatives are in [design Q19](docs/design/19-deployment-ui.md#revision-2026-10-25-what-was-actually-deployed). How to deploy from scratch is in [`infra/README.md`](infra/README.md).

## Development

| Command | What it runs |
|---|---|
| `make test` / `make test-db` / `make test-live` / `make test-e2e` | See above |
| `make test-web` | Frontend type check + adapter tests (Vitest) |
| `make lint` | ruff, formatting check, mypy (strict) |
| `make infra-plan` / `make infra-apply` / `make deploy` / `make infra-destroy` | Terraform and the k3s rollout ([`infra/README.md`](infra/README.md)) |

`POST /v1/debug/plan` runs a hand-written QueryPlan without the AI stages (disable with `ENABLE_DEBUG_ENDPOINTS=false`).

## Configuration

All settings come from environment variables (or `.env`); only `OPENAI_API_KEY` is required. Defaults are in [`backend/app/core/config.py`](backend/app/core/config.py), prices in [`pricing.yaml`](backend/app/core/pricing.yaml).

## Documentation

- [Assignment and requirements](docs/parts/README.md)
- [ClinicalTrials.gov API research](docs/api/contract.md) and [live probe findings](docs/api/live-probe.md)
- [System design (Q1-Q21)](docs/design/README.md)
- [Infrastructure and deployment](infra/README.md)
- [Implementation plan](docs/implementation-plan.md)

---

Built by [Adriel](https://engineeradriel.com).
