# ClinicalTrials.gov Query-to-Visualization Agent

Ask a question about clinical trials in plain words and get back a chart you can check. The backend turns the question into a structured, frontend-ready **visualization spec**, computed from [ClinicalTrials.gov API](https://clinicaltrials.gov/data-api/api) data, with **citations for every data point**: the NCT ID plus the exact record field and value that put the trial there. A web app renders the specs and lets you click any bar, point or link to see the trials behind it.

**Contents**

- [Live demo](#live-demo) · [Quick start](#quick-start-docker-compose) · [Configuration](#configuration)
- [What it does](#what-it-does) · [How it works](#how-it-works)
- [API](#api): [endpoints](#endpoints), [request](#post-v1query), [response](#response), [jobs](#background-jobs-202), [errors](#errors) · [Examples](#examples-real-outputs)
- [Key design decisions](#key-design-decisions) · [Testing and validation](#testing-and-validation) · [Limitations](#limitations) · [Future improvements](#future-improvements)
- [Tools used and integrity](#tools-used-and-integrity) · [Web app](#web-app) · [Deployment](#deployment) · [Development](#development) · [Documentation](#documentation)

## Live demo

The whole system is deployed, so you can try it without installing anything:

| | |
|---|---|
| **Web app** | https://trials.cheiron.engineeradriel.com |
| **API** | https://api.cheiron.engineeradriel.com |
| **API docs** | [API guide](https://trials.cheiron.engineeradriel.com/docs) with recorded examples; OpenAPI reference in [Swagger UI](https://api.cheiron.engineeradriel.com/docs) and [ReDoc](https://api.cheiron.engineeradriel.com/redoc) |
| **Infrastructure** | Kubernetes (k3s) on AWS EC2, with PostgreSQL in the cluster. Defined in Terraform and Kustomize; see [Deployment](#deployment). Fast mode is on. |
| **Source code** | https://github.com/lonestarx1/clinical-trials-visualization-agent |

## Quick start (Docker Compose)

Requirements: Docker with Compose v2, and an OpenAI API key.

```bash
cp .env.example .env    # then set OPENAI_API_KEY
make up                 # docker compose up -d --build --wait (postgres + api + web), then opens http://localhost:3000
curl -s localhost:8000/v1/query -H 'Content-Type: application/json' \
  -d '{"query": "How are breast cancer trials distributed across phases?"}'
# -> {"schema_version": "2.0", "result_id": "...", "status": "ok", "visualization": {"type": "bar_chart", ...}, "meta": {...}}
```

- Web app: http://localhost:3000 (questions can be shared as `?q=...` links)
- API guide: http://localhost:3000/docs · OpenAPI reference: http://localhost:8000/docs
- Stop with `make down`.

### Configuration

Settings come from environment variables (or `.env`); only `OPENAI_API_KEY` is required. All of them, with defaults, are in [`backend/app/core/config.py`](backend/app/core/config.py); model prices are in [`pricing.yaml`](backend/app/core/pricing.yaml). The ones you are most likely to change:

| Variable | Default | What it does |
|---|---|---|
| `OPENAI_API_KEY` | (required) | Key for the guard, planner and narrator |
| `GUARD_MODEL`, `PLANNER_MODEL`, `NARRATOR_MODEL` | `gpt-5.4-nano`, `gpt-5.4-mini`, `gpt-4o-mini` | Model per AI stage; each has a `*_FALLBACK_MODEL` (empty turns it off) |
| `LLM_DAILY_BUDGET_USD` | `100` | Daily AI spend cap; above it, questions that need a model call get `503 budget_exceeded` |
| `SYNC_MAX_SECONDS` | `60` | Questions estimated to take longer run as background jobs (202) |
| `CITATIONS_FULL_MAX` | `2000` | Most citations inlined by `citations: "full"` before it falls back to a sample |
| `ADMIN_TOKEN` | unset | Enables `GET /v1/usage` |
| `ENABLE_DEBUG_ENDPOINTS` | `true` | `POST /v1/debug/plan` (off in production) |
| `MIRROR_SYNC_ENABLED` | `false` | Load and keep our copy of ClinicalTrials.gov current (first load 23.4 minutes at half the API budget) |
| `FAST_MODE_ENABLED` | `false` | Accept `mode: "fast"`; needs the mirror |

![An answer: the question stays at the top, the chart below it, every bar traceable to its trials](docs/screenshots/answer.png)

## What it does

Language models are good at reading questions and bad at counting, so the work is split:

- **AI chooses, code computes.** The AI turns the question into a plan made of choices from fixed lists. Code fetches the data, computes every number and builds every citation, so no number or citation in a chart comes from a model. The AI's only free text is the chart title (numbers filled from placeholders, then checked) and the planner's short notes (`meta.assumptions`, and a refusal's reason and suggestion), which are shown as written and not checked.
- **Every number is traceable.** Each bar, bucket, node and edge lists the trials behind it, and each citation is checked against its source record before the response is sent.
- **Honest answers.** Counting rules are stated, excluded trials are counted, and a question we can't compute (such as an average duration) gets a refusal with a suggested alternative, not a different chart.
- **Exact data.** Charts come from ClinicalTrials.gov at request time, or from our daily copy checked against a live count (fast mode), never from a sample.

It draws 7 chart types (bar, grouped bar, time series, histogram, scatter, network, single metric) over trial counts, total and median enrollment, and distinct sponsors, drugs, countries and other entities. All 9 example questions in the assignment's appendix pass end to end against live data, at about $0.002 of AI cost each.

## How it works

```
request ─► validate (422) ─┬─► guard (AI, fail closed) ──────────────┐
                           └─► planner agent (AI + code tools) ──► gate (code) ─► compile ─► retrieve ─► aggregate ─► chart ─► verify citations ─► narrate (AI) ─► response
```

| Stage | Who | What |
|---|---|---|
| Guard | AI (`gpt-5.4-nano`) | Flags clearly malicious requests (prompt injection, misuse). Runs in parallel with planning. If it can't answer, the request is refused (503): **fail closed**. |
| Planner | AI agent (`gpt-5.4-mini`, LangGraph) | Turns words into **choices from fixed lists**: intent, chart type, dimension, measure, filters, comparison groups. Tools: `list_options`, `count_trials` (a real API count), `check_plan`, `submit_plan`. Bounded to 6 steps. |
| Gate | Code | Re-checks every plan: schema, chart compatibility, **entity grounding** (every drug, condition and sponsor must come from the question's own words), a stated reason for any filter the question didn't ask for, and **the plan must count what the question counts** ("how many sponsors" can't become a trial count). Structured request fields override the AI. |
| Compile, retrieve | Code | Plan -> a query in Essie, ClinicalTrials.gov's search syntax, built as an expression tree (text from the request can only ever be a quoted phrase) -> the API, with a global rate limiter, retries and a circuit breaker. Trials-per-year series are **counted with one call per year** when that is quicker than downloading every trial (2010-2020: 412 s → 57 s). |
| Aggregate, chart | Code | Every number. Explicit counting rules for multi-valued fields, and nothing silently dropped (`meta.excluded`). Runs off the event loop, so a large question doesn't stall other requests. |
| Verify | Code | Every citation excerpt is compared with the record it came from; a mismatch fails the request. |
| Narrate | AI (`gpt-4o-mini`) | Writes the chart title **with placeholders** filled from a fact sheet, so its numbers come from code. Checked for invented numbers, names not in the chart, evaluative claims, length and repeated phrases; one retry, then a template title. No free-text summary: it was prone to hallucination and not required ([decision](docs/design/04b-ai-validation.md#revision-2026-10-24-the-ai-summary-is-removed)). |

**Networks:** one entity dimension gives co-occurrence (drugs used together); two give links between kinds (sponsor - drug, condition - drug, sponsor - collaborator, investigator - site). Node and edge weights are distinct trials; edges also carry Jaccard similarity (shared trials divided by trials with either entity). The graph is pruned deterministically (recorded in `meta.network`) and communities are detected: in the melanoma example they separate lymphodepletion + IL-2 regimens, chemotherapy, checkpoint + BRAF/MEK therapy and peptide vaccines.

**Fast mode** (`mode: "fast"`, [Q22](docs/design/22-term-sets.md)): ClinicalTrials.gov's search still picks the trials, as sets of NCT IDs, so its synonym matching stays exact; a daily-synced copy in Postgres supplies their records for the same aggregation, citation check and title. It answers only if the copy holds the API's current data version and its count equals a live count; otherwise the answer is live, with a note in `meta.notes`. 10% of small fast answers are recomputed live in the background and compared.

## API

The [API guide](https://trials.cheiron.engineeradriel.com/docs) walks through requests, responses, jobs and citation paging. The full schema is in the [Swagger UI](https://api.cheiron.engineeradriel.com/docs), [ReDoc](https://api.cheiron.engineeradriel.com/redoc) and at `/openapi.json`; per chart type, see the [response schema design](docs/design/12-io-schema.md).

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/query` | Question -> chart spec (200), or a background job for broad questions (**202**) |
| `GET` | `/v1/jobs/{job_id}` | Job status, page progress, and the result when done (kept 24 h after finishing, then `410 expired`) |
| `DELETE` | `/v1/jobs/{job_id}` | Cancel a pending or running job (`status: cancelled`; the worker stops within about a second). Idempotent; anyone with the `job_id` can cancel, as with polling |
| `GET` | `/v1/results/{result_id}/citations?datum=<key>&cursor=&page_size=` | **Every** trial behind one data point (bar, bucket, node, edge...), keyset-paginated |
| `GET` | `/v1/options` | Dimensions, measures, chart types and filter values with labels (for pickers) |
| `GET` | `/v1/usage` | Today's LLM calls and cost (admin token) |
| `GET` | `/health` | Database and ClinicalTrials.gov status, data timestamp, and whether fast mode is ready |

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
| `mode` | `live` \| `fast` | no | Default `live`. See [fast mode](#how-it-works); `meta.data_source` says which mode answered |
| `citations` | `sample` \| `full` | no | Default `sample`. `full` inlines every citation, up to `CITATIONS_FULL_MAX` (2,000) per response; above that it falls back to a sample and `meta.citations.reason` says why |
| `citations_per_datum` | int 1-50 | no | Default 5 |
| `phase_mode`, `condition_source`, `include_unknown`, `edge_metric`, `hide_query_entity` | | no | See [request fields](docs/design/05-request-fields.md) |

Unknown fields are rejected (422).

### Response

```jsonc
{
  "schema_version": "2.0",
  "result_id": "d70db059-8f32-49a2-9fdc-231f5e3fd056",  // for the citations endpoint; null when nothing was stored
  "status": "ok",                       // or no_matching_trials | out_of_scope | could_not_interpret (200, visualization null, meta.details says why)
  "visualization": {
    "type": "bar_chart",
    "title": "...",
    "encoding": {                       // names the data key for every channel
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
    "data_source": "live",              // or "fast"
    "counting_rule": "...", "additive": true, "unique_trials": 16765, "excluded": [{"reason": "no start date", "count": 5}],
    "api_queries": [{"group": null, "url": "https://clinicaltrials.gov/api/v2/studies?...", "total_count": 16765}],
    "citations": {"requested": "sample", "applied": "sample", "reason": null}, "cache": {"plan": "miss", "result": "miss"},
    "data_timestamp": "...", "guard": {...}, "planner": {...}, "narration": {...},
    "usage": {"llm_calls": 4, "cost_usd": 0.0027}, "timings_ms": {...}, "trace_id": "..."
  }
}
```

A network graph's `data` is `{nodes, edges}` instead of rows ([example 5](docs/examples/5-drug-network.json)):

```jsonc
"data": {
  "nodes": [{"key": "drug:pembrolizumab", "id": "drug:pembrolizumab", "label": "pembrolizumab", "type": "drug",
             "weight": 250, "degree": 19, "community": 2, "is_query_entity": false, "citation_count": 250, "citations": [...]}],
  "edges": [{"key": "drug:ipilimumab|drug:nivolumab", "source": "drug:ipilimumab", "target": "drug:nivolumab",
             "weight": 122, "jaccard": 0.3873, "citation_count": 122, "citations": [...]}]
}
```

Each data point carries up to `citations_per_datum` citations inline (all of them with `citations: "full"`), plus `citation_count`. The full list always comes from the citations endpoint, with the response's `result_id` and the data point's `key`. For trials-per-year rows counted per year, the endpoint pages that year's API search on demand, so it still lists every trial ([Q14](docs/design/14-citations.md)). `meta.cache` says whether the plan and result came from cache (`hit`, `revalidated`, `miss`).

### Background jobs (202)

A question estimated above `SYNC_MAX_SECONDS` returns `202` with `{"job_id": "8c1f...", "status": "pending", "poll_url": "/v1/jobs/8c1f...", "estimated_seconds": 240}`. Polling `poll_url` gives `status` (`pending`, `running`, `succeeded`, `failed`, `cancelled`), `progress` (`pages_done` of `pages_total`), and `result` (the normal response above) or `error`.

### Errors

Errors share one body, routing errors included: `{"error": {"code", "message", "details", "trace_id"}}` with codes `invalid_request` (422), `rejected_by_policy` (400), `unauthorized` (401, `/v1/usage`), `not_found` (404, also unknown paths), `method_not_allowed` (405), `expired` (410, results and jobs), `too_many_requests` (429), `upstream_unavailable` / `llm_unavailable` / `safety_check_unavailable` / `budget_exceeded` (503) and `internal_error` (500). Once the daily AI budget is spent, `budget_exceeded` goes only to questions that need a model call: an exact repeat whose stored answer is still valid is answered without one.

## Examples (real outputs)

Generated by [`scripts/run_examples.py`](scripts/run_examples.py) against the running stack on 2026-10-24 with live data, and not edited by hand (a script later dropped `visualization.summary` for schema 2.0). They predate the model bake-off and fast mode, so their narrator is `gpt-5.4-nano` and they lack `meta.data_source` (default `live`).

| # | Request | Chart | Trials | Time |
|---|---|---|---|---|
| 1 | "How has the number of trials for this drug changed per year since 2015?" + `drug_name: Pembrolizumab` (the assignment's example) | [time_series](docs/examples/1-drug-trend.json) | 2,586 | 10 s |
| 2 | "How are breast cancer trials distributed across phases?" | [bar_chart](docs/examples/2-condition-phases.json) | 16,765 | 34 s |
| 3 | "Compare phases for trials involving pembrolizumab vs nivolumab." | [grouped_bar_chart](docs/examples/3-drug-comparison.json) | 4,228 | 15 s |
| 4 | "Which countries have the most recruiting trials for lung cancer?" | [bar_chart](docs/examples/4-recruiting-countries.json) | 2,182 | 9 s |
| 5 | "Which drugs frequently co-occur in combination studies for melanoma?" | [network_graph](docs/examples/5-drug-network.json) | 1,446 | 12 s |

## Key design decisions

The full reasoning, the alternatives and the links to requirements are in [docs/design](docs/design/README.md) (22 decisions, Q1-Q22). The main ones, each with what it costs:

- **AI chooses, code computes.** The planner picks from registry lists; all numbers and citations come from deterministic code; the AI writes only the title, with placeholders. *Cost:* only questions the registry can express are answered; a new dimension or measure needs code.
- **Live API by default.** Live charts are computed from ClinicalTrials.gov at request time, using the API's own drug and condition synonyms (a plain local text match misses about 20% of "lung cancer" trials, [Q21](docs/design/21-local-mirror-revisited.md)). *Cost:* answers take seconds to minutes and depend on the API, which allows about 10 requests per 10 s per IP.
- **Fast mode as a checked second path** ([Q22](docs/design/22-term-sets.md)): see [How it works](#how-it-works). *Cost:* a 600k-trial copy to keep in sync, and a swap (one trial in, one out) that keeps the count equal can pass the check; the shadow sample is the only net for that.
- **Refuse rather than substitute.** If no measure computes what was asked (e.g. an average duration), the answer says so and suggests the closest answerable question. *Cost:* some reasonable questions (shares, averages) get no chart.
- **Strict matching by default.** Drugs match intervention names (with the API's synonym expansion: "Keytruda" finds pembrolizumab trials); conditions are quoted phrases; "sponsor" means lead sponsor ([live probe](docs/api/live-probe.md)). *Cost:* fewer trials than a loose reading; `match_mode` and `sponsor_role` widen it.
- **Explicit counting rules.** 17% of trials have two phases, and trials list many drugs, conditions and countries. Every chart states its rule, whether bars add up (`meta.additive`) and how many distinct trials it covers. *Cost:* bars often don't sum to the total, which the client must show.
- **Defence in depth.** Validation, an AI guard, a strict plan schema, entity grounding, and an expression tree that makes query injection impossible (an injection attempt matched under 100 trials live, not all ~600k). *Cost:* a guard call per question, and a 503 when the guard is down.
- **Caching that stays correct.** Repeats reuse the stored plan and answer only if the data version is unchanged, or after revalidation (no matching trial updated since, and the same total). A repeat took 0.9 s instead of 13 s, with 1 model call instead of 4. *Cost:* 2 count calls per revalidation, and a 7-day ceiling after which the answer is recomputed.
- **Background jobs** for questions estimated above 60 s: 202 + polling, one active job per identical request, workers that claim jobs with Postgres `SKIP LOCKED` (so two never take the same job), retries and restart recovery. *Cost:* clients must poll, and the workers run inside the API process.
- **One registry.** A dimension is one entry (API fields, filter, enum, counting rule); options, validation, retrieval, aggregation and citations all read from it. *Cost:* each new dimension must fill every part of its entry.

## Testing and validation

The code was written test-first: each `test:` commit fails before the `feat:` commit that follows it. Expected values are worked out by hand or from direct API counts, never copied from the code's output.

| Suite | Command | What |
|---|---|---|
| Offline (CI) | `make test` | 589 unit, contract and integration tests: compiler strings and chart numbers worked out by hand from recorded real trials and fixtures, scripted fake models for the agents |
| Database (CI) | `make test-db` | 86 tests against Postgres: stored results and citation paging (including per-year rows paged from the API), caches, jobs (heartbeats, cancel, restart recovery, expiry), the daily budget, the mirror sync (first load, resume, daily update, removals), term sets, searches in SQL, and fast mode with each fallback to live |
| Live API | `make test-live` | 20 checks: query syntax against the real API, and **cross-checks**: our aggregated counts equal the API's own counts exactly, sponsor and per-year counts equal an independent tally of the raw records, and the mirror's counts equal the API's on about 100 filters and 6 term searches (needs a loaded mirror) |
| End to end | `make test-e2e` | 11 questions through the running stack, with real models and live data: **the 9 appendix questions all pass**, plus a sponsor-count question and a refused "average duration" |
| AI evaluation | `make eval`, `make bakeoff` | 42 planner questions, 36 labelled guard requests and 25 narrator fact sheets, scored against quality bars with the real models, 3 runs per case. **Every stage passes every bar**, and a measured bake-off chose the models. Reading the 75 narrator titles still found a misnamed condition and charts described wrongly ([results](docs/eval/README.md)) |
| Web (CI) | `make test-web` | 71 Vitest tests in 7 files: the chart adapter against the example responses, theme contrast gates, the mode switch, the API proxy, and the question, evidence and API-guide helpers |

CI never calls ClinicalTrials.gov or a model: the live, end-to-end and evaluation suites are opt-in.

## Limitations

- **Broad live questions are slow.** Questions that need per-trial data across hundreds of thousands of trials (e.g. sponsors per year) take minutes, as background jobs. Fast mode can answer many of them from the copy, but answers live when a check fails, the question covers over 300,000 trials, or a new search term matches over 20,000.
- **Title checks miss some errors.** The narrator checks catch invented numbers and names, but not a partly wrong name ("Spinal Muscular Dystrophy" for atrophy) or a title that misdescribes its chart.
- **Planner misses.** The planner sometimes drops the condition from a question (about 1 run in 3 on two of 42 questions). The evaluation sets are our own and small, so their numbers are indicative.
- Shares and percentages are not a measure: "what share of trials have results, by phase" shows counts with and without results side by side.
- Sponsor names are not merged across spellings ("Merck Sharp & Dohme LLC" vs "Merck & Co."). Drug grouping by MeSH (the NLM's medical vocabulary) inherits its quirks: "aldesleukin" and "Interleukin-2" can be separate nodes. The queried entity is flagged in a network by name, so "Keytruda" doesn't flag the pembrolizumab node.
- A misspelled drug or condition gets `no_matching_trials` with per-search counts, but no "did you mean" suggestion.
- **Designed but not built:** the page-level API cache (L1) and request coalescing; the `traces` table (traces are in logs and `meta`); the periodic purge of expired results, jobs and cache rows (expired ones answer 410 but stay in the database); and, for fast mode, the weekly full re-sync, the nightly term-set pre-warm, the `registry.drift` table (drift goes to the logs) and alerts.
- The rate limiters and job workers are in-process (one instance). Several instances would need a shared store such as Redis.

## Future improvements

- A live end-to-end set of about 60 questions, with a report ([Q18](docs/design/18-testing.md)); today's has 11.
- Two narrator checks: compare every name in the title with the chart's names exactly, and require the title to name every dimension.
- The designed-but-not-built items above, sponsor name merging, and shares as a measure.
- Task-scoped authorization with [Tenuo](https://tenuo.ai/), once the agents can change things or other agents call the API ([plan](docs/implementation-plan.md#whats-planned)).

## Tools used and integrity

- **Tools:** Claude Code (Anthropic) as the coding assistant; OpenAI models inside the product for the guard, planner and title stages ([design Q20](docs/design/20-model-selection.md)).
- **Designed deliberately:** the decisions in [`docs/design/`](docs/design/README.md), made one question at a time with reasons and alternatives: the architecture (the AI chooses, code computes), the schemas, the counting rules, the citation model, fast mode and the deployment.
- **Generated and adapted:** code, tests and docs were drafted with Claude Code, then reviewed, tested and revised, test-first where possible.
- **How correctness was checked:** see [Testing and validation](#testing-and-validation): hand-worked expected values, counts cross-checked against the API's own, every citation checked against its raw record, and an [AI evaluation set](docs/eval/README.md) per AI stage.

**The git history shows how it was built.** Nothing was squashed; every change went through a pull request with small commits: research and design first, then milestones M0 to M5 (skeleton, data layer, charts, AI stages, networks, storage and jobs, web app), then fixes found against live data, the UI, deployment, fast mode and the docs. Browse the [merged pull requests](https://github.com/lonestarx1/clinical-trials-visualization-agent/pulls?q=is%3Apr+is%3Amerged) or run `git log --reverse`. The full disclosure is in the [integrity note](docs/parts/08-integrity-note.md).

## Web app

A Next.js and Apache ECharts app in [`frontend/`](frontend/), built for people who need to trust the numbers:

- **Ask in plain words**, or refine with filters shown as removable chips; a Live/Fast switch, and each answer says where its trials came from. The question stays above its answer and can be edited in place (`/`).
- **Every chart traces back to the trials.** Click any bar, point, node or link: a drawer lists the trials behind it, with the record lines that put each one there highlighted, and pages through all of them.
- **Readable charts:** a colour-blind-safe palette, direct value labels, named network clusters, a **table view**, and plain-language notes on what was counted and the exact ClinicalTrials.gov queries.
- **10 colour themes** plus "Automatic", each passing contrast checks in CI (text ≥ 12:1, secondary text ≥ 7:1); shareable links (`?q=`, `&d=` for one data point), PNG download, keyboard and screen-reader support, and phone layouts.

The charts are drawn from the response's `encoding` ([`lib/adapter.ts`](frontend/lib/adapter.ts), tested against the example responses), plus a few fixed keys documented in the [schema design](docs/design/12-io-schema.md): `key` (histogram bin labels, and matching edges to nodes), and for networks the node `label` and `is_query_entity` and the edge `weight`. The app proxies `/api/*` to the backend, so the API address is a runtime setting (`API_BASE_URL`).

| Home | Evidence for one bar | Drug network |
|---|---|---|
| ![Home screen with example questions](docs/screenshots/home.png) | ![Evidence drawer: the trials behind "China", with the matching record line highlighted](docs/screenshots/evidence.png) | ![Melanoma drug co-occurrence network with named clusters](docs/screenshots/network.png) |

| Theme picker | Midnight theme | Phone |
|---|---|---|
| ![The theme dropdown with 10 themes](docs/screenshots/themes.png) | ![An answer in the Midnight dark theme](docs/screenshots/dark.png) | ![An answer on a phone](docs/screenshots/phone.png) |

## Deployment

It runs on **Kubernetes (k3s) on one EC2 t3.medium**, defined in **Terraform** (network, node, IAM, ECR, Secrets Manager, DNS) and **Kustomize** (Postgres, API, web, Ingress with Let's Encrypt). The API pod keeps the mirror synced and serves fast mode. `make deploy` builds, pushes and rolls out through an SSM tunnel: there's no SSH and no public Kubernetes API.

**Why this setup:** low cost (about $1.50/day) for a short build window. k3s is real Kubernetes with the same manifests as EKS, without EKS's $2.40/day control-plane fee; the Kustomize base also has an EKS overlay.

**In production** it would run on EKS across three zones, with RDS for Postgres, background workers scaled on queue depth, one rate limiter shared by all pods (ClinicalTrials.gov limits per IP), CloudFront, WAF and an ALB in front, External Secrets, and GitOps deploys with Argo CD. The reasons are in [design Q19](docs/design/19-deployment-ui.md#revision-2026-10-25-what-was-actually-deployed); deploying from scratch is in [`infra/README.md`](infra/README.md).

## Development

| Command | What it runs |
|---|---|
| `make up` / `make down` / `make logs` | Start, stop and follow the Compose stack |
| `make test` / `make test-db` / `make test-live` / `make test-e2e` | See [testing](#testing-and-validation) |
| `make test-web` | Frontend type check + tests (Vitest) |
| `make lint` / `make fmt` | ruff, formatting check and mypy (strict) / auto-format |
| `make infra-plan` / `make infra-apply` / `make deploy` / `make infra-destroy` | Terraform and the k3s rollout ([`infra/README.md`](infra/README.md)) |

`POST /v1/debug/plan` runs a hand-written QueryPlan without the AI stages (off with `ENABLE_DEBUG_ENDPOINTS=false`).

Layout: [`backend/`](backend/) (FastAPI, Python 3.12, `uv`), [`frontend/`](frontend/) (Next.js), [`infra/`](infra/) (Terraform and Kubernetes), [`scripts/`](scripts/) (example runs and the API probe), [`docs/`](docs/).

## Documentation

| Document | What it covers |
|---|---|
| [API guide](https://trials.cheiron.engineeradriel.com/docs) | How to call the API: requests, responses, jobs, citation paging |
| [Swagger UI](https://api.cheiron.engineeradriel.com/docs) and [ReDoc](https://api.cheiron.engineeradriel.com/redoc) | The full OpenAPI reference |
| [Assignment](docs/assignment.md) and [requirement breakdown](docs/parts/README.md) | The original brief and every requirement it implies |
| [Integrity note](docs/parts/08-integrity-note.md) | Tools used, how correctness was checked, what was designed vs generated |
| [System design (Q1-Q22)](docs/design/README.md) | Each design decision, with reasons, alternatives and requirement links |
| [How it was built](docs/implementation-plan.md) | Milestones, the test-first workflow, and what's planned |
| [AI evaluation](docs/eval/README.md) | Case sets, quality bars, results and the model bake-off |
| [ClinicalTrials.gov API research](docs/api/contract.md) and [live probe](docs/api/live-probe.md) | What the API documents, and what it does when probed |
| [Example responses](docs/examples/) | Five real responses from the running stack |
| [Infrastructure and deployment](infra/README.md) | Terraform, k3s and deploying from scratch |

---

Built by [Adriel](https://engineeradriel.com).
