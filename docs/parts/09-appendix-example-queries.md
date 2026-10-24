# Appendix: example question classes

## 1. Summary

The brief lists example questions to show the range of questions it has in mind. Supporting all of them is not required, and other questions and charts are welcome. In our own words, the examples are:

| Class | Example questions |
|---|---|
| Time trends | How the number of trials for a given drug changed per year since 2015; how many trials started each year for a given condition |
| Distributions | How a condition's trials are spread across phases; the most common intervention types for a drug's or condition's trials |
| Comparisons | Phases of trials for drug A vs drug B; sponsor categories across two conditions |
| Geographic patterns | The countries with the most recruiting trials for a condition |
| Relationships and networks | A network of sponsors and drugs for a condition's trials; drugs that often appear together in combination studies (a drug-drug network) |

## 2. Atomic requirements

| ID | Level | Requirement |
|---|---|---|
| PA-0 | SHOULD | Cover the **breadth** shown: 5 classes. Not all 9 questions are required, but each class should be covered. |
| PA-1..9 | SHOULD | The 9 questions below each map to a plan (see table). |
| PA-10 | MAY | Go beyond these (e.g. histogram/scatter on numeric fields). |

## 3. Question-by-question breakdown

This was the first proposal, written before the API fields were verified. How each question is now handled is in the appendix table of [`../design/requirements-coverage.md`](../design/requirements-coverage.md); all 9 pass end to end.

| ID | Question | Filters | Group-by / structure | Measure | Chart | Details to watch |
|---|---|---|---|---|---|---|
| PA-1 | Trials for *[drug]* per year **since 2015** | intervention = drug; start year >= 2015 | start year | count of trials | `time_series` | "Since 2015" sets the lower bound; the upper bound is the current year. Should empty years show as 0? (Yes, fill gaps.) Partial dates count by year. Future "anticipated" start dates? Note in `meta`. |
| PA-2 | Trials **started** each year for *[condition]* | condition | start year | count | `time_series` | Same as PA-1. Broad conditions mean large result sets, so the volume/cap strategy matters here. |
| PA-3 | *[condition]* trials **across phases** | condition | phase | count | `bar_chart` | Multi-phase trials (PHASE1+PHASE2): count as "Phase 1/Phase 2" or in both? Decide and document. "NA" (not applicable) phase. Sort in natural phase order, not by count. |
| PA-4 | **Most common intervention types** for *[drug/condition]* | drug or condition | intervention type (DRUG, BIOLOGICAL, DEVICE, ...) | count of trials having that type | `bar_chart` (sorted desc) | One trial has several interventions: count trials per type, not interventions. "Most common" means sort descending, maybe top-N. |
| PA-5 | Compare phases: **Drug A vs Drug B** | two intervention groups | phase × group | count | `grouped_bar_chart` | Two separate API searches, one per group. A trial using both drugs appears in both groups: note it. Consistent phase order. |
| PA-6 | Compare **sponsor categories** across **two conditions** | two condition groups | lead sponsor class × group | count | `grouped_bar_chart` | "Sponsor categories" = sponsor class (INDUSTRY, NIH, OTHER, ...); map to readable labels. Maybe show percentages too (groups differ in size); add a `normalize` option. |
| PA-7 | Countries with the most **recruiting** trials for *[condition]* | condition; status = RECRUITING | country | count of trials with ≥1 site in that country | `bar_chart` (sorted desc, top-N) | A trial lists many sites/countries: count each trial once per country. Status filter: overall status or per-site status? (Note: recruiting status may exist at site level too; verify.) Possibly a map type later. |
| PA-8 | Network **sponsors <-> drugs** for *[condition]* | condition | bipartite: sponsor nodes, drug nodes; edge = trial links them | edge weight = number of trials | `network_graph` | Lead sponsor only, or collaborators too? Drug names need normalisation (dose text, brand vs generic). Exclude placebo. Prune to top-N. |
| PA-9 | Drugs that **co-occur in combination studies** (drug <-> drug) | trials with ≥2 drug interventions (optionally a condition scope) | co-occurrence: drug nodes; edge = both in the same trial | edge weight = number of trials | `network_graph` | No condition given means all of ClinicalTrials.gov, which is too large. Require or default a scope (e.g. a condition or drug), and say so in `meta`. Exclude placebo/standard-of-care terms. Self-loops removed. |

## 4. What it means

- All 9 fit **one plan shape**: `filters + (optional) comparison groups + dimension(s) + measure -> chart type`. That is the "one coherent approach" Part 4 asks for. If our plan schema can express all 9 without special cases, coverage is solved by design.
- Repeated hard parts, in priority order:
  1. Multi-valued fields: phases, interventions, countries, conditions.
  2. Large result sets for broad conditions (pagination / caps / count queries).
  3. Name normalisation for drugs and sponsors (affects PA-8, PA-9, and drug filters).
  4. Comparison = several sub-queries, merged into one chart.
- PA-9 names no scope, so it tests whether a "too broad" question is handled sensibly instead of timing out.

## 5. Acceptance checks

- [ ] Each of PA-1..PA-9 runs end to end with a real entity filled in (e.g. pembrolizumab, nivolumab, breast cancer, lung cancer, Alzheimer's disease). Results go to a test/eval script.
- [ ] 5 of them (one per class) become the official `examples/` for Part 6.
- [ ] Each multi-valued counting rule is documented in the README and reported in `meta`.
- [ ] Too-broad queries (PA-9 with no scope) return a sensible answer with a note, not a timeout. (Decided in [design Q6](../design/06-retrieval.md): instead of forcing a scope, such questions run as a background job, and the planner may suggest a narrower scope.)
