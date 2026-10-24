# Design Q12: Request and response formats

Status: **Decided** (2026-10-24). The detailed field-level schema is generated from the code (Pydantic -> OpenAPI/JSON Schema) and documented in the README.

## Decision

**Our own schema, in Vega-Lite style**, not real Vega-Lite specs.

- **Why our own:** Vega-Lite can't express network graphs. With our own schema, every chart type, including networks, shares one consistent envelope, and we control citations, metadata and versioning.
- **Why Vega-Lite style:** the channel names (`x`, `y`, `color`) and field descriptors (`field`, `type`) are familiar to frontend engineers. The assignment's example uses the same idea (`encoding.x.field`).
- Considered: emitting real Vega-Lite for the non-network charts. Rejected for now (two formats to maintain); a Vega-Lite **export** for non-network charts is listed as future work.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/query` | Main entry. `200` with a result, or `202` with a background job (Q6) |
| `GET` | `/v1/jobs/{job_id}` | Poll a job: `pending` / `running` (progress) / `succeeded` (result) / `failed` (error). A finished job is kept 24 h, then `410 expired` (Q17) |
| `GET` | `/v1/results/{result_id}/citations` | Full, paginated citation list for one data point (Q14) |
| `GET` | `/v1/options` | Registry: dimensions, measures, chart types, filter enums + labels, compatibility rules. The frontend builds pickers from it. |
| `GET` | `/v1/usage` | Today's AI calls and cost per stage and model; needs the admin token (`ADMIN_TOKEN`), otherwise 401 |
| `GET` | `/health` | Liveness/readiness (DB, ClinicalTrials.gov reachability, data timestamp) |
| `GET` | `/docs`, `/openapi.json` | Auto-generated API docs and schemas |

The request schema is in Q5 (`05-request-fields.md`).

## Response envelope (same for every chart type)

**Revision (2026-10-24):** `visualization.summary` was removed and `schema_version` went from `"1.0"` to `"2.0"`, because removing a field breaks clients ([Q4b revision](04b-ai-validation.md#revision-2026-10-24-the-ai-summary-is-removed)).

```json
{
  "schema_version": "2.0",
  "result_id": "uuid (null when no result is stored)",
  "status": "ok | no_matching_trials | out_of_scope | could_not_interpret",
  "visualization": {
    "type": "bar_chart | grouped_bar_chart | time_series | histogram | scatter_plot | network_graph | metric",
    "title": "string (AI-written, validated)",
    "encoding": { "...": "per type, see below" },
    "data": "per type, see below"
  },
  "meta": {
    "interpretation": { "intent": "...", "dimension": "...", "measure": "...", "chart_type_source": "ai | user | fallback" },
    "filters": { "drug_name": ["pembrolizumab"], "...": "applied filters, after merging" },
    "assumptions": ["..."],
    "warnings": ["..."],
    "counting_rule": "Each trial is counted once per country where it has at least one site.",
    "additive": true,
    "unique_trials": 2928,
    "excluded": [ { "reason": "no start date", "count": 5 } ],
    "sort": { "by": "x | y", "order": "asc | desc | natural" },
    "api_queries": [ { "group": "all", "url": "https://clinicaltrials.gov/api/v2/studies?...", "total_count": 2928 } ],
    "data_timestamp": "2026-10-23T09:00:04",
    "retrieved_at": "2026-10-24T08:12:00Z",
    "source": "clinicaltrials.gov",
    "narration": { "model": "...", "attempts": 1, "fallback": false },
    "usage": { "llm_calls": 3, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "plan_cache_hit": false },
    "citations": { "requested": "sample | full", "applied": "sample | full", "per_datum": 5, "reason": "null, or why applied differs (Q14)" },
    "network": "network graphs only: nodes/edges before and after pruning, thresholds, community algorithm (Q13)",
    "group_overlap": "comparisons only: overlapping trial counts per pair of groups (Q9)",
    "cache": { "plan": "hit | miss", "result": "hit | miss | revalidated" },
    "details": "non-ok statuses only, see below",
    "trace_id": "uuid",
    "timings_ms": { "plan": 0, "count": 0, "retrieve": 0, "aggregate": 0, "narrate": 0, "total": 0 }
  }
}
```

**Background job (202):** `{ "job_id": "uuid", "status": "pending", "poll_url": "/v1/jobs/{job_id}", "estimated_seconds": 240 }`. Polling returns `{ "job_id", "status", "progress": { "stage", "pages_done", "pages_total" }, "result": <the normal response above> | null, "error": <error body, Q17> | null }`.

When `status` isn't `ok`, `visualization` is `null` and `meta.details` explains why:

| `status` | `meta.details` |
|---|---|
| `no_matching_trials` | `{ "search_counts": [ { "group": null, "count": 0 } ] }`: one entry per search (one per comparison group). Per-search, not per-filter, counts: see the revision below |
| `out_of_scope` | `{ "reason": "...", "suggestion": "a question we can answer" }` (`suggestion` is optional) |
| `could_not_interpret` | `{ "errors": ["..."], "best_attempt": { ...the last plan... } }` |

## Encoding channel descriptor

```json
{ "field": "trial_count", "type": "quantitative | nominal | ordinal | temporal",
  "label": "Number of trials", "unit": "trials", "sort": "ascending | descending | natural | null",
  "time_unit": "year (temporal only)" }
```

## Per chart type

| Type | `encoding` channels | `data` |
|---|---|---|
| `bar_chart` | `x` (nominal/ordinal category), `y` (quantitative measure) | `[{ <x>: "Phase 2", <y>: 1269, "citations": [...] }]` |
| `grouped_bar_chart` | `x` (category), `y` (measure), `color` (group/series) | `[{ <x>: "Phase 2", <color>: "Pembrolizumab", <y>: 1269, "citations": [...] }]` (long format) |
| `time_series` | `x` (temporal, `time_unit: "year"`), `y` (measure), optional `color` (series) | `[{ <x>: "2019", <y>: 312, "estimated_count": 0, "citations": [...] }]` (zero-filled) |
| `histogram` | `x` (bin range of a numeric field), `y` (count) | `[{ "bin_start": 0, "bin_end": 50, "count": 410, "is_overflow": false, "citations": [...] }]` |
| `scatter_plot` | `x`, `y` (quantitative), `id` (`nct_id`), optional `color` | `[{ "nct_id": "NCT...", <x>: 120, <y>: 36.5, "citations": [...] }]` |
| `network_graph` | flat channels: `node_id` (`id`), `node_label` (`label`), `node_size` (`weight`), `node_color` (`community` for one entity type, `type` for two), `edge_source` (`source`), `edge_target` (`target`), `edge_width` (`weight`, or `jaccard` with `edge_metric: jaccard`) | `{ "nodes": [{ "key", "id", "label", "type", "weight", "degree", "community", "is_query_entity", "citations"... }], "edges": [{ "key", "source", "target", "weight", "jaccard", "citations"... }] }` |
| `metric` | `value` (quantitative, with `unit`) | `[{ "value": 2457, "label": "Recruiting breast cancer trials", "citations": [...] }]` |

Notes:
- Data rows are **flat records** whose keys are named in `encoding` (as in the assignment's example). Exceptions: `network_graph` (nodes/edges) and `histogram` (fixed bin keys, declared in `encoding`).
- Every data point (row, node or edge) also has `key` (its stable id, used by the citations endpoint), `citation_count`, `citations` and `citations_truncated` (Q14).
- Field names are stable snake_case and are listed in `encoding`. The renderer never has to guess a key.
- Citation format is decided in Q14.

## Versioning

The response includes `schema_version` (now `"2.0"`), so frontends can detect breaking changes.

## Revision (2026-10-25): network encoding and `no_matching_trials` details, as built

The built responses differed from this design in two places. The code was kept and this document now describes it:

- **Network channels are flat** (`node_id`, `node_size`, `edge_width`...), not nested `node: {...}` / `edge: {...}` objects. Every chart's `encoding` is then the same shape (a map from channel name to one field descriptor), so a renderer reads all of them the same way. Nodes and edges also carry `key`, `degree`, `community`, `is_query_entity` and `jaccard` (Q13). See [`docs/examples/5-drug-network.json`](../examples/5-drug-network.json).
- **`no_matching_trials` gives per-search counts** (`meta.details.search_counts`), not per-filter counts. The searches are already counted before retrieval, so this costs nothing; per-filter counts would need one more count call per filter and are future work.

## Requirement links

P3-5..P3-12 (output components, metadata, schema docs), P4-1, P4-2 (structured spec, multiple types), P7-12, P7-13 (I/O design).
