# Design Q4b: Validating AI output (plan, title)

Status: **Decided** (2026-10-24). All 9 checks adopted. **Revised** the same day: the AI summary was removed (see [the revision](#revision-2026-10-24-the-ai-summary-is-removed) below).

The AI produces exactly two things: the **QueryPlan** (planning agent) and the chart **title** (narration). Each one passes through code checks before it's used. (The first version also had the AI write a one-sentence **summary**; that was removed.)

## Revision (2026-10-24): the AI summary is removed

Decided after live testing.

**Decision:** the narrator writes **only the chart title**. The one-sentence summary under the title is gone: from the narrator prompt and its JSON schema, from the template fallback, from the response (`visualization.summary`) and from the web UI. This supersedes the summary parts of this file, Q2 D2.3, the narration row in Q3, the `summary` field in Q12, the summary row in Q17 and the "title + summary in one call" narrator in Q20.

**Why:**
- **Free-text summaries are hallucination-prone.** Even with the fact sheet, placeholders and the V6-V8 checks, a full sentence can imply patterns, comparisons or causes that the chart doesn't show. The checks catch wrong numbers, unknown names and banned words, not a misleading framing. Live testing also produced awkward, repetitive sentences.
- **The assignment only requires a human-readable `title`** (P3-7, `docs/assignment.md` 3.2). The summary added risk without adding required value.
- **Cheaper and faster:** fewer output tokens and less narrator time. The chart itself, the data table, the counting rule and the "How this was answered" notes already explain the result.

**What stays:** the title is still AI-written, with the same code checks: the fact sheet and placeholders (V5, numbers only come from placeholders), the number check (V6), the name check (V7, names must be in the chart or the filters), the banned evaluative words (V8), the length limit (90 characters) and the repeated-phrase check (a placeholder wrapped in its own words). If narration still fails after one retry, the **deterministic template title** is used (V9).

**Compatibility:** removing a response field breaks clients, so `schema_version` goes from `"1.0"` to `"2.0"`. The stored-result code version goes to `0.6.0`, so cached answers that still carry a summary aren't reused.

## A. Plan checks (code gate after the planning agent)

| # | Check | Catches | On failure |
|---|---|---|---|
| V1 | **Schema + compatibility rules** (Q3, Q4a): strict types, enums, bounds, chart-type rules, 2-4 groups | Malformed or impossible plans | Error returned to the agent (inside its step budget) |
| V2 | **Entity grounding:** every free-text entity term (drug, condition, sponsor, country, group label entity) must appear in the user's `query` or structured fields, allowing small spelling differences (case/accent/punctuation-insensitive, small edit distance) | The AI adding entities nobody asked for | Error to agent; at the gate: reject the plan |
| V3 | **Non-empty search:** each entity filter must match > 0 trials (via `count_trials`, cached) | Typos, nonsense terms | Error to agent with the count; at the gate: structured "no matching trials" response |
| V4 | **Unrequested filters need a stated reason:** any filter not traceable to the query or fields (e.g. a year range, a status) needs a matching entry in `assumptions[]` | Hidden, silent narrowing of the question | Error to agent; at the gate: reject the plan |

## B. Narration (title; the summary was removed in the 2026-10-24 revision)

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

The narrator gets **only** the fact sheet (plus chart type and dimension labels). It writes the title (originally also the summary) using **placeholders**, e.g.:

> `"Pembrolizumab trials peaked at {max_value} in {max_bucket}"`

Code replaces the placeholders with the fact values. **The numbers are correct by construction.** The AI chooses words, never values.

### Checks on the rendered text

| # | Check | Catches | On failure |
|---|---|---|---|
| V6 | **Leftover number check:** any number written literally (not via a placeholder) must equal a fact value (tolerance for rounding/percent formatting). Years must be within the data or filter range. | Made-up or misremembered numbers | Retry, then fallback |
| V7 | **Name check:** every category/entity named in the text must exist in the chart's data labels or the applied filters | Mentioning things not in the chart | Retry, then fallback |
| V8 | **Banned claims:** deny-list of evaluative or medical-conclusion words ("effective", "best", "safe", "proves", "cure", "superior", ...) and unknown placeholders | Clinical conclusions the data can't support | Retry, then fallback |
| V9 | **Failure policy:** one retry with the specific errors; if it still fails, fall back to a **template** title built from the same facts (originally also a template summary), and `meta.narration.fallback = true` with the reasons | Persistent narration failure | Always returns valid text |

Additional structural limits: title ≤ ~90 characters. Only known placeholders are allowed. ~~Summary is 1 sentence, ≤ ~200 characters.~~ (superseded 2026-10-24: the AI summary was removed, see [Q4b revision](04b-ai-validation.md#revision-2026-10-24-the-ai-summary-is-removed))

## Traceability

`meta` records, for each AI step:
- model name
- attempts and tool calls (for the planner)
- which checks failed and why
- whether a fallback was used

This is the evidence for "how we validated correctness" (Part 8) and for "include validation or constraints" (Part 7).

## Requirement links

P7-4, P7-5, P7-6 (hallucination, validation, planning), P8-2 (validation evidence), P2-2 (authoritative data: numbers never come from the AI).
