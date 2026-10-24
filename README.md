# ClinicalTrials.gov Query-to-Visualization Agent

A backend service that turns a natural-language question about clinical trials into a structured, frontend-ready **visualization spec**, computed from live [ClinicalTrials.gov API](https://clinicaltrials.gov/data-api/api) data, with **citations for every data point** (NCT ID + the exact field and value it came from).

```
POST /v1/query  {"query": "How are breast cancer trials distributed across phases?"}
-> 200 {"status": "ok", "visualization": {"type": "bar_chart", "title": ..., "encoding": ..., "data": [...]}, "meta": {...}}
```

> **Status:** core service complete (milestones M0-M2): question -> validated plan -> live data -> chart spec with citations, plus AI title and summary. In progress: network graphs and scatter plots (M3), result storage and background jobs (M4), UI (M5), deployment (M6). See [the implementation plan](docs/implementation-plan.md).

## Quick start

Requirements: Docker with Compose v2.

```bash
cp .env.example .env    # then set OPENAI_API_KEY
make up                 # builds and starts postgres + api, waits until healthy
curl -s localhost:8000/v1/query -H 'Content-Type: application/json' \
  -d '{"query": "Which countries have the most recruiting trials for lung cancer?"}'
```

Interactive API docs (OpenAPI): http://localhost:8000/docs

## How it works

```
request ─► validate (422) ─┬─► guard (AI, fail closed) ──────────────┐
                           └─► planner agent (AI + code tools) ──► gate (code) ─► compile ─► retrieve ─► aggregate ─► chart ─► verify citations ─► narrate (AI) ─► response
```

| Stage | Who | What |
|---|---|---|
| Guard | AI (`gpt-5.4-nano`) | Flags clearly malicious requests (prompt injection, misuse). Runs in parallel with planning. If it can't answer, the request is refused (503): **fail closed**. |
| Planner | AI agent (`gpt-5.4-mini`, LangGraph) | Turns words into **choices from fixed lists**: intent, chart type, dimension, measure, filters, comparison groups. Tools: `list_options`, `count_trials` (a real API count), `check_plan`, `submit_plan`. Bounded to 6 steps. |
| Gate | Code | Re-checks every plan: schema, chart compatibility, **entity grounding** (every drug/condition/sponsor must come from the user's words), unrequested filters need a stated reason. Structured request fields override the AI. |
| Compile, retrieve | Code | Plan -> Essie query tree (user text can only ever be a quoted phrase) -> ClinicalTrials.gov, with a global rate limiter, retries and a circuit breaker. |
| Aggregate, chart | Code | Every number. Explicit counting rules for multi-valued fields, nothing silently dropped (`meta.excluded`). |
| Verify | Code | Every citation excerpt is compared with the record it came from; a mismatch fails the request. |
| Narrate | AI (`gpt-5.4-nano`) | Writes the title and one-sentence summary **with placeholders** filled from a fact sheet, so numbers are correct by construction. Checked for invented numbers, names not in the chart and evaluative claims; one retry, then a template. |

The AI never produces a number or a citation. Models are configurable per stage (`GUARD_MODEL`, `PLANNER_MODEL`, `NARRATOR_MODEL`, each with a fallback model).

## API

### `POST /v1/query`

| Field | Type | Required | Notes |
|---|---|---|---|
| `query` | string | yes | 1-1,000 characters |
| `drug_name`, `condition`, `sponsor`, `country` | string or string[] | no | OR within a field; up to 10 terms of up to 200 characters. **Override the question.** |
| `trial_phase` | string[] | no | `PHASE1`... or labels like `"Phase 3"` |
| `status` | string[] | no | Overall status, e.g. `RECRUITING` or `"Recruiting"` |
| `start_year`, `end_year` | int | no | Start-date range |
| `compare` | 2-4 x `{label, drug_name?, condition?, sponsor?, country?}` | no | Comparison groups |
| `chart_type` | enum | no | `bar_chart`, `grouped_bar_chart`, `time_series`, `histogram`, `metric` (`scatter_plot`, `network_graph` in M3); checked for compatibility |
| `top_n` | int 1-50 | no | |
| `match_mode` | `strict` \| `broad` | no | Drug/condition matching (default `strict`) |
| `sponsor_role` | `lead` \| `any` | no | Default `lead` |
| `citations_per_datum` | int 1-50 | no | Default 5 |
| `phase_mode`, `condition_source`, `include_unknown` | | no | See [request fields](docs/design/05-request-fields.md) |

Unknown fields are rejected (422). Full schema: `/openapi.json`.

### Response

```jsonc
{
  "schema_version": "1.0",
  "status": "ok",                       // or no_matching_trials | out_of_scope | could_not_interpret (200, visualization null)
  "visualization": {
    "type": "bar_chart",
    "title": "...", "summary": "...",
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

Per chart type: [response schema design](docs/design/12-io-schema.md). Errors share one body: `{"error": {"code", "message", "details", "trace_id"}}` with codes `invalid_request` (422), `rejected_by_policy` (400), `upstream_unavailable` / `llm_unavailable` / `safety_check_unavailable` (503) and `internal_error` (500).

## Examples (real outputs)

Generated by [`scripts/run_examples.py`](scripts/run_examples.py) against the running stack on 2026-10-24 with live data; never edited by hand.

| # | Request | Chart | Trials | Time |
|---|---|---|---|---|
| 1 | "How has the number of trials for this drug changed per year since 2015?" + `drug_name: Pembrolizumab` (the assignment's example) | [time_series](docs/examples/1-drug-trend.json) | 2,586 | ~10 s |
| 2 | "How are breast cancer trials distributed across phases?" | [bar_chart](docs/examples/2-condition-phases.json) | 16,765 | ~32 s |
| 3 | "Compare phases for trials involving pembrolizumab vs nivolumab." | [grouped_bar_chart](docs/examples/3-drug-comparison.json) | 4,228 | ~16 s |
| 4 | "Which countries have the most recruiting trials for lung cancer?" | [bar_chart](docs/examples/4-recruiting-countries.json) | 2,182 | ~11 s |
| 5 | "What is the distribution of enrollment sizes for Phase 3 Alzheimer's disease trials?" | [histogram](docs/examples/5-enrollment-histogram.json) | 372 | ~6 s |

AI cost per question: about $0.003 (measured, `meta.usage`).

## Key design decisions

The full reasoning, alternatives and requirement links are in [docs/design](docs/design/README.md) (20 decisions). The main ones:

- **AI chooses, code computes.** The planner picks from registry lists; all numbers and citations come from deterministic code. Narration uses placeholders.
- **Live API, exact answers.** Every chart is computed from ClinicalTrials.gov at request time, never sampled. A local mirror was seriously considered and rejected (legal uncertainty about bulk copying, operational weight).
- **Strict matching by default.** Drugs match intervention names (with the API's own synonym expansion: "Keytruda" finds pembrolizumab trials); conditions are quoted phrases; "sponsor" means lead sponsor. `match_mode` / `sponsor_role` widen it. Measured in the [live probe](docs/api/live-probe.md).
- **Explicit counting rules.** 17% of trials have two phases, and trials list many drugs, conditions and countries. Every chart states its rule, whether bars add up (`meta.additive`) and how many distinct trials it covers.
- **Defence in depth.** Request validation, an AI guard, a strict plan schema, entity grounding, and an expression tree that makes query injection impossible. Verified live: an injection attempt matched under 100 trials, not all ~600k.
- **One registry.** A dimension is one entry (API fields, filter, enum, counting rule); options, validation, retrieval, aggregation and citations all read from it.

## Testing and validation

Written test-first (each `test:` commit fails before the `feat:` commit that follows it).

| Suite | Command | What |
|---|---|---|
| Offline (CI) | `make test` | ~290 unit, contract and integration tests: compiler strings written by hand, chart numbers worked out by hand from 8 recorded real trials, scripted fake models for the agents |
| Database | `make test-db` | Against Postgres |
| Live API | `make test-live` | Query syntax against the real API, and a **cross-check**: our aggregated counts equal the API's own counts exactly |
| End to end | `make test-e2e` | The 9 appendix questions through the running stack, real models and live data: **7 pass**; the 2 network questions wait for M3 |

## Limitations (current)

- Network graphs and scatter plots aren't built yet (M3); the planner currently answers network questions with a bar chart of one side.
- Very broad questions (100k+ trials needing per-trial data) run synchronously and can take minutes; background jobs come in M4.
- Sponsor names are not merged across spellings ("Merck Sharp & Dohme LLC" vs "Merck & Co."); MeSH grouping inherits MeSH mapping errors.
- The rate limiter is in-process (one instance).

## Development

| Command | What it runs |
|---|---|
| `make test` / `make test-db` / `make test-live` / `make test-e2e` | See above |
| `make lint` | ruff, formatting check, mypy (strict) |

`POST /v1/debug/plan` runs a hand-written QueryPlan without the AI stages (disable with `ENABLE_DEBUG_ENDPOINTS=false`).

## Configuration

All settings come from environment variables (or `.env`); only `OPENAI_API_KEY` is required. Defaults are in [`backend/app/core/config.py`](backend/app/core/config.py), prices in [`pricing.yaml`](backend/app/core/pricing.yaml).

## Documentation

- [Assignment and requirements](docs/parts/README.md)
- [ClinicalTrials.gov API research](docs/api/contract.md) and [live probe findings](docs/api/live-probe.md)
- [System design (Q1-Q20)](docs/design/README.md)
- [Implementation plan](docs/implementation-plan.md)
