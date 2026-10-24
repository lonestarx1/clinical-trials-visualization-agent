# Part 4: Visualization Requirements

## 1. Source text (verbatim)

> - The answer to the query must be a **visualization** (via structured specification).
> - You may support any visualization types, but your system should aim to support **multiple** types, such as:
>   - bar chart / grouped bar chart
>   - timeline/time series
>   - scatter plot
>   - histogram
>   - network graph (entities like drugs, sponsors, conditions, investigators, sites)
>
> **Design goal:** Cover as many query types as possible with a **single coherent approach** and support **multiple visualization types**. Submissions that implement richer visualizations (e.g., meaningful network graphs) and broader query coverage will be scored higher than those that only support one chart type.

## 2. Atomic requirements

| ID | Level | Requirement | Source phrase |
|---|---|---|---|
| P4-1 | MUST | The answer **is** a visualization, given as a structured spec (not prose, not an image). | "The answer to the query must be a visualization (via structured specification)." |
| P4-2 | SHOULD | Support **multiple** visualization types. | "should aim to support multiple types" |
| P4-2a | SHOULD | Bar chart **and** grouped bar chart | list |
| P4-2b | SHOULD | Timeline / time series | list |
| P4-2c | SHOULD | Scatter plot | list |
| P4-2d | SHOULD | Histogram | list |
| P4-2e | SHOULD | Network graph, with entities such as **drugs, sponsors, conditions, investigators, sites** | list |
| P4-3 | SHOULD | Use **one coherent approach** across all query types. No per-question code paths. | "single coherent approach" |
| P4-4 | SHOULD | **Richer** visualizations; network graphs must be **meaningful**. | "richer visualizations (e.g., meaningful network graphs)" |
| P4-5 | SHOULD | **Broad** query coverage. | "broader query coverage will be scored higher" |

## 3. What it really means

- The grader names network graphs **twice** here and again in Part 7. **A good network graph is clearly the differentiator.**
- What makes a network "meaningful" (our reading):
  - Nodes are real entities with a **type**: drug, sponsor, condition, site, investigator.
  - Edges have a **weight** that means something, such as the number of trials linking the two.
  - Noise is controlled: top-N nodes, a minimum edge weight, placebo and comparator terms excluded, and names lightly normalised.
  - Each edge can be traced to the trials that created it (links to Part 5).
  - The output says how the graph was pruned, so the viewer knows what's hidden.
- "Single coherent approach" means one engine of the form **filters × dimension(s) × measure -> chart type**, where adding a new dimension (e.g. "intervention type") is a registry entry, not new code paths.

## 4. Chart type mapping (proposal)

| Chart type | Typical question | Built from |
|---|---|---|
| `bar_chart` | distribution across one categorical dimension (phase, status, sponsor class, country, intervention type) | count per category |
| `grouped_bar_chart` | comparison of 2+ groups across one dimension (Drug A vs Drug B by phase) | count per (group, category) |
| `time_series` | trend per year/month | count per time bucket (optionally per series) |
| `histogram` | distribution of a numeric field (enrollment size, trial duration, number of sites) | binned numeric values |
| `scatter_plot` | relation between two numeric fields per trial (enrollment vs duration) | one point per trial |
| `network_graph` | co-occurrence / relationships (sponsor <-> drug, drug <-> drug, condition <-> drug) | nodes + weighted edges |
| (maybe) `metric` | single-number answer | one count |

Scatter and histogram need **numeric** fields. Likely candidates (to verify in the API):
- enrollment count
- start and completion dates, giving duration
- number of locations
- number of arms

## 5. Ambiguities and proposed decisions

- **Who picks the chart type: LLM or rules?**
  - Proposed: the LLM proposes the **analysis intent** (trend / distribution / comparison / relationship / numeric distribution / correlation) and the dimensions.
  - A **deterministic rule table** then maps the intent and dimension types to the chart type, and checks it. For example, `time_series` needs a time dimension, and `network_graph` needs two entity dimensions.
  - This avoids "LLM picked a pie chart for a time trend".
- **"Timeline"** could also mean a Gantt-style chart of individual trials (start -> end). Possible addition: a `timeline` type for small result sets. Low priority unless time allows.
- **Pie charts** aren't listed, so skip them. A bar chart covers the same need.

## 6. Acceptance checks

- [ ] At least 5 chart types work end to end: bar, grouped bar, time series, histogram, network. Scatter as well, if time allows.
- [ ] Each appendix question class gets a suitable chart type (see 09).
- [ ] The network graph has typed nodes, weighted edges, pruning rules in `meta`, and per-edge citations.
- [ ] Adding a new dimension needs only a registry entry plus a test, which the README shows.
- [ ] Tests verify the chart type is chosen by rules from the intent and dimensions.
