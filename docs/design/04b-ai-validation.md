# Design Q4b: Validating AI Output (plan, title, summary)

Status: **Decided** (2026-10-24, with the user). All 9 checks adopted.

The AI produces exactly three things: the **QueryPlan** (planning agent), the **title**, and the **summary** (narration). Each one passes through code checks before it's used.

## A. Plan checks (code gate after the planning agent)

| # | Check | Catches | On failure |
|---|---|---|---|
| V1 | **Schema + compatibility rules** (Q3, Q4a): strict types, enums, bounds, chart-type rules, 2-4 groups | Malformed or impossible plans | Error returned to the agent (inside its step budget) |
| V2 | **Entity grounding:** every free-text entity term (drug, condition, sponsor, country, group label entity) must appear in the user's `query` or structured fields, allowing small spelling differences (case/accent/punctuation-insensitive, small edit distance) | The AI adding entities nobody asked for | Error to agent; at the gate: reject the plan |
| V3 | **Non-empty search:** each entity filter must match > 0 trials (via `count_trials`, cached) | Typos, nonsense terms | Error to agent with the count; at the gate: structured "no matching trials" response |
| V4 | **Unrequested filters need a stated reason:** any filter not traceable to the query or fields (e.g. a year range, a status) needs a matching entry in `assumptions[]` | Hidden, silent narrowing of the question | Error to agent; at the gate: reject the plan |

## B. Narration (title + summary)

### V5: Fact sheet (the core mechanism)

After aggregation, code computes a **fact sheet** from the chart data. Each fact has an ID and a value. Examples:

| Fact ID | Example value | Applies to |
|---|---|---|
| `total` | 2,928 | all |
| `n_buckets` | 12 | bar / time series |
| `max_bucket`, `max_value` | "2021", 312 | bar / time series |
| `min_bucket`, `min_value` | "2015", 41 | bar / time series |
| `top_k_items`, `top_k_values` | ["Phase 2", "Phase 1"], [1269, 575] | bar |
| `share_of_top` | 43.3% | bar |
| `first_bucket`, `last_bucket`, `trend_direction` | "2015", "2026", "increasing" | time series |
| `group_totals` | {A: 2993, B: 2036} | grouped bar |
| `n_nodes`, `n_edges`, `strongest_edge`, `top_degree_node` | ... | network |
| `median`, `p25`, `p75`, `n_points` | ... | histogram / scatter |
| `applied_filters` | {drugs: [...], years: ...} | all |

The narrator gets **only** the fact sheet (plus chart type and dimension labels). It writes the title and summary using **placeholders**, e.g.:

> `"Pembrolizumab trials peaked at {max_value} in {max_bucket}"`

Code replaces the placeholders with the fact values. **The numbers are correct by construction.** The AI chooses words, never values.

### Checks on the rendered text

| # | Check | Catches | On failure |
|---|---|---|---|
| V6 | **Leftover number check:** any number written literally (not via a placeholder) must equal a fact value (tolerance for rounding/percent formatting). Years must be within the data or filter range. | Made-up or misremembered numbers | Retry, then fallback |
| V7 | **Name check:** every category/entity named in the text must exist in the chart's data labels or the applied filters | Mentioning things not in the chart | Retry, then fallback |
| V8 | **Banned claims:** deny-list of evaluative or medical-conclusion words ("effective", "best", "safe", "proves", "cure", "superior", ...) and unknown placeholders | Clinical conclusions the data can't support | Retry, then fallback |
| V9 | **Failure policy:** one retry with the specific errors; if it still fails, fall back to a **template** title/summary built from the same facts, and `meta.narration.fallback = true` with the reasons | Persistent narration failure | Always returns valid text |

Additional structural limits: title ≤ ~90 characters; summary is 1 sentence, ≤ ~200 characters. Only known placeholders are allowed.

## Traceability

`meta` records, for each AI step:
- model name
- attempts and tool calls (for the planner)
- which checks failed and why
- whether a fallback was used

This is the evidence for "how we validated correctness" (Part 8) and for "include validation or constraints" (Part 7).

## Requirement links

P7-4, P7-5, P7-6 (hallucination, validation, planning), P8-2 (validation evidence), P2-2 (authoritative data: numbers never come from the AI).
