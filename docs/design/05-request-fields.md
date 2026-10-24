# Design Q5: Structured request fields and how they merge with the question

Status: **Decided** (2026-10-24)

## Fields (names from the assignment; entity fields accept a string or a list = OR)

| Field | Type | Required | Validation |
|---|---|---|---|
| `query` | string | **yes** | 1-1,000 chars after trimming; not blank |
| `drug_name` | string \| string[] | no | each 1-200 chars; max 10 items |
| `condition` | string \| string[] | no | same |
| `sponsor` | string \| string[] | no | same |
| `country` | string \| string[] | no | same |
| `trial_phase` | Phase enum[] | no | `EARLY_PHASE1, PHASE1, ..., PHASE4, NA` (labels like "Phase 3" also accepted and normalised) |
| `status` | Status enum[] | no | API status values |
| `start_year`, `end_year` | int | no | 1900 <= year <= current year + 10; `start_year <= end_year` |
| `compare` | 2-4 x `{label, drug_name? , condition?, sponsor?, country?}` | no | each group needs >= 1 entity; labels unique |
| `chart_type` | chart enum | no | overrides the AI; compatibility still checked (200 `could_not_interpret` if impossible: it depends on the dimension the planner picks, [Q3 revision](03-ai-vs-code.md#optional-request-override)) |
| `top_n` | int | no | 1-50 |
| `match_mode` | `strict` \| `broad` | no | default `strict` (drug and condition matching); see Q7 |
| `sponsor_role` | `lead` \| `any` | no | default `lead`; see Q7 |
| `citations` | `sample` \| `full` | no | default `sample`; `full` is size-guarded by the backend (Q14) |
| `citations_per_datum` | int | no | 1-50, default 5 (Q14) |
| `phase_mode` | `combined` \| `split` | no | default `combined` (Q9) |
| `condition_source` | `mesh` \| `raw` | no | default `mesh` (Q11) |
| `include_unknown` | bool | no | default `true`: show the "Not reported" bucket (Q10) |
| `edge_metric` | `count` \| `jaccard` | no | networks only, default `count` (Q13) |
| `hide_query_entity` | bool | no | networks only, default `false` (Q13) |

Rendering/analysis options (`top_n`, `phase_mode`, `condition_source`, `include_unknown`, `edge_metric`, `hide_query_entity`) map 1:1 to `QueryPlan.options` (Q4a). A value in the request overrides the AI.

Unknown fields are rejected (422).

The web app offers **pickers** for these fields, built from `GET /v1/options`, to reduce mistakes. The backend still validates everything, because the API is public.

## Merge rules

1. **Fields override the AI.** The planning agent receives the fields as fixed facts and can't change them. Code merges them into the plan again at the gate.
2. **Conflicts:** if the query says "lung cancer" but `condition` says "breast cancer", the field wins and `meta.warnings` records the conflict.
3. **References:** "this drug" / "these conditions" in the query resolve to the corresponding fields. The agent is told which fields are present.
4. **Fields without a real question** (e.g. `drug_name` + "show me trials"): the AI picks a sensible default chart (e.g. distribution by phase) and records it in `assumptions`.
5. **Grounding (V2):** field values count as grounded entities.

## What if field data is bad or unusable?

Handled in three layers. **We never silently drop or "fix" a user-provided field**, because fields are authoritative.

| Layer | Example | Behaviour |
|---|---|---|
| **1. Invalid input** (shape/type/range) | `start_year: 2030, end_year: 2020`; phase `"Phase 7"`; empty string; 500-char drug name; unknown field | **422** with a per-field error (`loc`, `msg`). Fail fast, no AI call, no API call. |
| **2. Sanitised input** (valid but needs cleaning) | `"  Pembrolizumab\n"`; Unicode look-alikes; Essie operator characters/keywords inside a term (`"aspirin) OR (ALL"`, `AREA[...]`) | Trim + Unicode-normalise. **Escape/quote every user term** before it goes into an Essie expression, so user text can never change the API query's structure (query-injection protection). The cleaned value is echoed in `meta.filters`. |
| **3. Valid but unusable** (matches nothing) | `drug_name: "pembrolizumb"` (typo); `drug_name: X` + `condition: Y` with no overlap | Checked with a cheap `count_trials` before the full fetch. Returns **200** with `visualization: null`, `status: "no_matching_trials"`, and the count of each search in `meta.details.search_counts` (`[{"group": null, "count": 0}]`, one entry per comparison group). *As built:* per-search, not per-filter, counts; per-filter counts would cost one extra count call per filter and are future work. The AI may **not** rewrite a user field. (A "did you mean" suggestion would need a reliable source of names; listed as future work.) |

Fields that are valid but irrelevant to the question are still applied as filters, with a note in `meta.assumptions`.

## Requirement links

P3-1..P3-4 (inputs and validation docs), P3-14, P7-3 (real-world data), P7-8 (robustness), P7-12 (unambiguous schemas).
