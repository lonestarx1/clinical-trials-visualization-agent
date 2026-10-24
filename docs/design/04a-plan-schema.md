# Design Q4a: The QueryPlan (what the planning agent must submit)

Status: **Decided** (2026-10-24)

## Shape

```
QueryPlan
  scope:          "in_scope" | "out_of_scope"
  scope_reason:   string (required if out_of_scope)
  intent:         trend | distribution | top_n | comparison | geographic | network
                  | numeric_distribution | numeric_relationship | single_number
  chart_type:     bar_chart | grouped_bar_chart | time_series | histogram
                  | scatter_plot | network_graph | metric
  filters:        Filters (shared by all groups)
  groups:         [] or 2-4 x { label: string, filters: Filters }   (comparisons only)
  dimension:      registry key, e.g. "phase", "start_year", "country", "sponsor", "drug"
  dimension_2:    optional registry key (series split, or second node type of a network)
  measure:        trial_count | total_enrollment | median_enrollment
  options:        { top_n?, histogram_bins?, phase_mode? (combined|split, Q9), condition_source? (mesh|raw, Q11),
                    include_unknown?, show_empty? (Q10), network_min_edge_weight?, edge_metric? (count|jaccard),
                    hide_query_entity? (Q13) }
  assumptions:    [string]   (how the question was read; shown in meta)

Filters
  drugs:          [string]   free text as the user wrote it (checked via count_trials)
  conditions:     [string]   free text
  sponsors:       [string]   free text
  sponsor_role:   "lead" (default) | "any"   (Q7)
  match_mode:     "strict" (default) | "broad"  (drugs/conditions, Q7)
  countries:      [string]   free text
  phases:         [Phase enum]
  statuses:       [Status enum]
  study_types:    [StudyType enum]
  sponsor_classes:[AgencyClass enum]
  start_year_min: int (bounded)
  start_year_max: int (bounded)
```

(Further filter fields follow the Q1 dimension list: age group, sex, healthy volunteers, allocation, masking, primary purpose, results reported, US state. Every one is an enum or boolean.)

**As built (2026-10-25)** ([`plan.py`](../../backend/app/schemas/plan.py)), additions to the shape above:
- `measure` also takes `distinct_count`: distinct entities (sponsors, drugs, ...) per bucket, with `options.count_entity` and an optional `options.min_trials` (1-1,000). Both options are rejected with any other measure.
- `scope_suggestion` (up to 300 chars): for an out-of-scope answer, the closest question the tool can answer, shown in `meta.details.suggestion`. `scope_reason` is up to 500 chars; `assumptions` up to 10 entries; `options.histogram_bins` 2-50; `options.top_n` 1-50.
- `filters.us_states` is free text like `countries`, not an enum, and is grounded by V2 ([Q4b](04b-ai-validation.md)).
- `options.show_empty` lists every value of an enum dimension, with 0 where no trial has it ([Q10](10-missing-partial-estimated.md), D10.9).

## Decisions

| # | Decision |
|---|---|
| D4a.1 | Every field is an **enum or a bounded number**, except entity terms (drugs, conditions, sponsors, countries). Those are free text, and the agent verifies them with `count_trials`. |
| D4a.2 | **Strict schema:** unknown keys are rejected. |
| D4a.3 | **Comparison groups: 2-4.** No groups = a normal single-population question. |
| D4a.4 | **OR within a filter, AND across filters.** `drugs: ["pembrolizumab","nivolumab"]` = trials with either drug. `drugs` + `conditions` = both must match. "A vs B" is expressed as `groups`, not as a list. |
| D4a.5 | `assumptions[]` is the AI's only free-text explanation channel. It's shown in `meta`, never used for computation. *As built:* `scope_reason` and `scope_suggestion` are free text too, shown in `meta.details` for out-of-scope answers, and AI-made group labels become series names. None of it is checked against the data ([Q3](03-ai-vs-code.md#code-decides-everything-that-affects-the-numbers)). |
| D4a.6 | Structured request fields are merged into `filters` by code and **override** the AI (Q3). |

## Requirement links

P3-1..P3-4 (inputs), P7-5 (validation/constraints), P7-12 (unambiguous schemas).
