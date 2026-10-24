# Design Q5: Structured request fields and how they merge with the question

Status: **Decided** (2026-10-24)

## Fields (names from the assignment; entity fields accept a string or a list = OR)

Checked against [`backend/app/schemas/request.py`](../../backend/app/schemas/request.py) on 2026-10-25. Every field except `query` is optional.

| Field | Type | Default | Validation |
|---|---|---|---|
| `query` | string | (required) | Whitespace trimmed, then 1-1,000 chars |
| `drug_name` | string \| string[] | `[]` | Max 10 items. Each is cleaned (NFKC; quotes, backslashes and control characters become spaces; whitespace collapsed), then must be 1-200 chars |
| `condition` | string \| string[] | `[]` | same |
| `sponsor` | string \| string[] | `[]` | same |
| `country` | string \| string[] | `[]` | same |
| `trial_phase` | Phase[] | `[]` | A list (a bare string is rejected) of `NA, EARLY_PHASE1, PHASE1 ... PHASE4`. Labels such as "Phase 3" are accepted, ignoring case, spaces and punctuation |
| `status` | Status[] | `[]` | A list of the 14 API overall-status codes; labels accepted the same way |
| `start_year`, `end_year` | int | none | 1900 to current year + 10; `start_year <= end_year`. They bound the start year |
| `compare` | 2-4 x `{label, drug_name?, condition?, sponsor?, country?}` | `[]` | `label` 1-100 chars, unique; each group needs >= 1 entity; entity fields follow the rules above. Unknown keys rejected |
| `chart_type` | chart enum | none | Overrides the AI; compatibility still checked (200 `could_not_interpret` if impossible: it depends on the dimension the planner picks, [Q3 revision](03-ai-vs-code.md#optional-request-override)) |
| `top_n` | int | none | 1-50 |
| `match_mode` | `strict` \| `broad` | `strict` | Drug and condition matching; see Q7 |
| `sponsor_role` | `lead` \| `any` | `lead` | See Q7 |
| `mode` | `live` \| `fast` | `live` | `fast` reads the matching trials from the local mirror ([Q22](22-term-sets.md)); it answers live, with a note in `meta.notes`, when any check fails or the server has fast mode off. `meta.data_source` says which mode answered |
| `citations` | `sample` \| `full` | `sample` | `full` falls back to a sample above 2,000 inline citations (`CITATIONS_FULL_MAX`, Q14) |
| `citations_per_datum` | int | 5 | 1-50 (Q14) |
| `phase_mode` | `combined` \| `split` | `combined` | Q9 |
| `condition_source` | `mesh` \| `raw` | `mesh` | Q11 |
| `include_unknown` | bool | `true` | Show the "Not reported" bucket (Q10) |
| `edge_metric` | `count` \| `jaccard` | `count` | Networks only (Q13) |
| `hide_query_entity` | bool | `false` | Networks only (Q13) |

Rendering/analysis options (`top_n`, `phase_mode`, `condition_source`, `include_unknown`, `edge_metric`, `hide_query_entity`) map 1:1 to `QueryPlan.options` (Q4a). A value in the request overrides the AI. Only fields the request actually sends override the plan: an omitted field leaves the planner's choice, and the defaults above apply when neither sets it. `mode`, `citations` and `citations_per_datum` don't enter the plan; they choose how the answer is fetched and cited.

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
| **2. Sanitised input** (valid but needs cleaning) | `"  Pembrolizumab\n"`; Unicode look-alikes; Essie operator characters/keywords inside a term (`"aspirin) OR (ALL"`, `AREA[...]`) | Trim + Unicode-normalise. **Escape/quote every user term** before it goes into an Essie expression, so user text can never change the API query's structure (query-injection protection). The cleaned value is echoed in `meta.filters`. *As built:* NFKC normalisation; quotes, backslashes and control characters become spaces (dropped, not escaped); whitespace is collapsed; then each term is always one quoted phrase (Q7, D7.1). |
| **3. Valid but unusable** (matches nothing) | `drug_name: "pembrolizumb"` (typo); `drug_name: X` + `condition: Y` with no overlap | Checked with a cheap `count_trials` before the full fetch. Returns **200** with `visualization: null`, `status: "no_matching_trials"`, and the count of each search in `meta.details.search_counts` (`[{"group": null, "count": 0}]`, one entry per comparison group). The AI may **not** rewrite a user field. *As built:* this answer comes only when **every** search matches nothing; a comparison where one group matches nothing is still charted, with that group at 0. **Not built:** per-filter counts (one extra count call per filter) and a "did you mean" suggestion (it would need a reliable source of names). |

Fields that are valid but irrelevant to the question are still applied as filters, with a note in `meta.assumptions`. *As built:* code always applies them; the note is up to the planner and isn't enforced.

## Requirement links

P3-1..P3-4 (inputs and validation docs), P3-14, P7-3 (real-world data), P7-8 (robustness), P7-12 (unambiguous schemas).
