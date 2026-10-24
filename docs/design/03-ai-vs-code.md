# Design Q3: What the AI decides vs what code decides

Status: **Decided** (2026-10-24)

## Rule of thumb

> The AI turns words into **choices from fixed lists**. Code turns choices into **numbers**.

## The AI decides (language understanding only, always from fixed option lists)

| Decision | Source of options |
|---|---|
| In scope / out of scope (+ reason) | Scope rules (Q1) |
| Intent: trend, distribution, top-N, comparison, geographic, network, numeric distribution, numeric relationship, single number | Enum |
| **Chart type** | Enum: `bar_chart`, `grouped_bar_chart`, `time_series`, `histogram`, `scatter_plot`, `network_graph`, `metric` |
| Entities as the user wrote them: drug, condition, sponsor, country terms; comparison groups ("A vs B") | Free text, checked with `count_trials` |
| Dimension(s) and measure | Registry keys |
| Filters: status, phase, year range, ... | Enum values / bounded integers |
| Chart title (narration stage) | Free text with fact placeholders, sanity-checked (Q4). The one-sentence summary was removed 2026-10-24 ([Q4b revision](04b-ai-validation.md#revision-2026-10-24-the-ai-summary-is-removed)) |

## Code decides (everything that affects the numbers)

- Compatibility of the chart type with the intent and dimensions (rules below)
- Merging structured request fields: **user fields override the AI's choices**
- Defaults: year range, top-N size, time granularity
- API search syntax (strict vs broad match), field selection, paging, caps
- Counting rules, normalisation, missing-value handling
- Sorting, zero-filling empty time buckets, network pruning
- **All numbers and all citations**

## Chart-type compatibility rules (enforced by code)

| Chart type | Requires |
|---|---|
| `time_series` | A time dimension (start year, first-posted year) |
| `bar_chart` | One categorical dimension |
| `grouped_bar_chart` | One categorical dimension **plus** either comparison groups or a second categorical dimension |
| `histogram` | One numeric field (enrollment, duration, number of sites) |
| `scatter_plot` | Two numeric fields |
| `network_graph` | Two entity dimensions (or one, for co-occurrence such as drug ↔ drug) |
| `metric` | No dimension |

## Planning = a bounded agent with code tools

The planning stage (pipeline stages 2-3) is an **AI agent with tools**, not a single call.

| Tool | Purpose |
|---|---|
| `list_options` | Returns the registry: dimensions, measures, chart types, filters, and the compatibility rules |
| `check_plan` | Runs every validation and compatibility check; returns specific, actionable errors |
| `count_trials` | Cheap API count (~0.35 s). Catches typos, empty and huge result sets **before** committing (e.g. "pembrolizumb -> 0 trials") |
| `submit_plan` | Final answer; ends the loop |

### Guardrails

1. **Code gate after the agent.** Whatever is submitted is re-validated by code, whether or not the agent called `check_plan`. The agent's self-check is never trusted alone.
2. **Bounded loop:** at most ~6 tool calls plus a time limit. Over the limit, return a structured "could not interpret" response with the best attempt and the errors.
3. **Tools never give the agent chart data.** `count_trials` only supports planning. Chart numbers always come from the deterministic pipeline (stages 4-8).
4. **Every tool call is traced** (name, args, result, latency) into `meta` and the logs.
5. **Fallback on an incompatible chart type:** if the gate still rejects only the chart type, code uses the default chart for the intent and says so in `meta`.

### Optional request override

`chart_type` is an optional request field. If set, it overrides the AI. Code still checks compatibility, and an impossible combination returns 422.

## Why an agent here (tradeoff)

- **For:** Part 7 grades "sensible planning and reasoning steps, along with appropriate tools". The agent catches bad entities and impossible charts **before** fetching data. Explicit chart requests are respected.
- **Against:** more latency and cost, and a variable number of steps. Mitigated by the step limit, the cheap tools, and caching `count_trials`.
- Narration (stage 9) stays a **single call** followed by code checks (Q4). It doesn't need tools.

## Requirement links

P1-2, P1-4 (interpret, identify chart type), P7-4..P7-6 (hallucination, validation, planning + tools), P3-5..P3-9 (spec fields).
