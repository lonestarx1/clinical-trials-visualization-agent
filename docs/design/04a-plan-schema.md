# Design Q4a: The QueryPlan (what the planning agent must submit)

Status: **Decided** (2026-10-24, with the user)

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

## Decisions

| # | Decision |
|---|---|
| D4a.1 | Every field is an **enum or a bounded number**, except entity terms (drugs, conditions, sponsors, countries). Those are free text, and the agent verifies them with `count_trials`. |
| D4a.2 | **Strict schema:** unknown keys are rejected. |
| D4a.3 | **Comparison groups: 2-4.** No groups = a normal single-population question. |
| D4a.4 | **OR within a filter, AND across filters.** `drugs: ["pembrolizumab","nivolumab"]` = trials with either drug. `drugs` + `conditions` = both must match. "A vs B" is expressed as `groups`, not as a list. |
| D4a.5 | `assumptions[]` is the AI's only free-text explanation channel. It's shown in `meta`, never used for computation. |
| D4a.6 | Structured request fields are merged into `filters` by code and **override** the AI (Q3). |

## Requirement links

P3-1..P3-4 (inputs), P7-5 (validation/constraints), P7-12 (unambiguous schemas).
