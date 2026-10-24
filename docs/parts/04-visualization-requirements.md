# Part 4: Visualization requirements

## 1. Summary

- The answer to a question is a visualization, given as a structured specification.
- Any chart types may be supported, but the service should aim for **several**: bar and grouped bar charts, time series or timelines, scatter plots, histograms, and network graphs of entities such as drugs, sponsors, conditions, investigators and sites.
- **Design goal:** cover as many kinds of question as possible with **one coherent approach**, across several chart types. Richer visualizations (meaningful network graphs in particular) and broader coverage score higher than support for a single chart type.

## 2. Atomic requirements

| ID | Level | Requirement |
|---|---|---|
| P4-1 | MUST | The answer **is** a visualization, given as a structured spec (not prose, not an image). |
| P4-2 | SHOULD | Support **several** visualization types. |
| P4-2a | SHOULD | Bar chart **and** grouped bar chart |
| P4-2b | SHOULD | Timeline or time series |
| P4-2c | SHOULD | Scatter plot |
| P4-2d | SHOULD | Histogram |
| P4-2e | SHOULD | Network graph, with entities such as **drugs, sponsors, conditions, investigators and sites** |
| P4-3 | SHOULD | Use **one coherent approach** across all query types. No per-question code paths. |
| P4-4 | SHOULD | **Richer** visualizations; network graphs must be **meaningful**. |
| P4-5 | SHOULD | **Broad** query coverage. |

## 3. What it means

- Network graphs are named here and again in Part 7. **A good network graph is the clearest differentiator.**
- What makes a network "meaningful" (our reading):
  - Nodes are real entities with a **type**: drug, sponsor, condition, site, investigator.
  - Edges have a **weight** that means something, such as the number of trials linking the two.
  - Noise is controlled: top-N nodes, a minimum edge weight, placebo and comparator terms excluded, and names lightly normalised.
  - Each edge can be traced to the trials that created it (see Part 5).
  - The output says how the graph was pruned, so the viewer knows what is hidden.
- "One coherent approach" means one engine of the form **filters x dimensions x measure -> chart type**, where adding a new dimension (e.g. intervention type) is a registry entry, not a new code path.

## 4. Chart type mapping

The first proposal, kept for reference. The final set is 7 chart types ([design Q1](../design/01-scope.md), [Q12](../design/12-io-schema.md)): all of the rows below, with `metric` included.

| Chart type | Typical question | Built from |
|---|---|---|
| `bar_chart` | distribution across one categorical dimension (phase, status, sponsor class, country, intervention type) | count per category |
| `grouped_bar_chart` | comparison of 2 or more groups across one dimension (drug A vs drug B by phase) | count per (group, category) |
| `time_series` | trend per year or month | count per time bucket (optionally per series) |
| `histogram` | distribution of a numeric field (enrollment size, trial duration, number of sites) | binned numeric values |
| `scatter_plot` | relation between two numeric fields per trial (enrollment vs duration) | one point per trial |
| `network_graph` | co-occurrence and relationships (sponsor-drug, drug-drug, condition-drug) | nodes and weighted edges |
| `metric` | single-number answer | one count |

Scatter plots and histograms need **numeric** fields. The candidates were:
- enrollment count
- start and completion dates, giving duration
- number of locations
- number of arms

## 5. Ambiguities and decisions

- **Who picks the chart type: the LLM or rules?**
  - First proposal: the LLM proposes the **analysis intent** (trend, distribution, comparison, relationship, numeric distribution, correlation) and the dimensions, and a **deterministic rule table** maps them to the chart type.
  - **Decided ([design Q3](../design/03-ai-vs-code.md)):** the LLM picks the chart type from a fixed list, and a code gate checks it against compatibility rules (for example, `time_series` needs a time dimension and `network_graph` needs two entity dimensions). If only the chart type is rejected, code falls back to the default chart for the intent and says so in `meta`. This avoids, for example, a pie chart for a time trend.
- **"Timeline"** could also mean a Gantt-style chart of individual trials (start to end). It was a low-priority option and was not built; time trends use `time_series`.
- **Pie charts** aren't listed, so they are skipped. A bar chart covers the same need.

## 6. Acceptance checks

- [ ] At least 5 chart types work end to end: bar, grouped bar, time series, histogram, network. Scatter as well, if time allows.
- [ ] Each appendix question class gets a suitable chart type (see the appendix breakdown).
- [ ] The network graph has typed nodes, weighted edges, pruning rules in `meta`, and per-edge citations.
- [ ] Adding a new dimension needs only a registry entry plus a test.
- [ ] Tests verify that the chart type is checked against the intent and dimensions.
