# Design Q9: Counting rules for multi-valued fields

Status: **Decided** (2026-10-24)

Live data shows most dimensions are multi-valued: 17% of pembrolizumab trials have 2 phases, trials have up to 54 drugs, 101 conditions and 1,660 sites (live-probe §5). Every dimension declares its counting rule in the registry, and every response states it in `meta`.

## Rules

| # | Dimension(s) | Rule | Bars add up to the total? |
|---|---|---|---|
| D9.1 | **Phase** (default `phase_mode: combined`) | Each trial counts **once**. A multi-phase trial gets a combined bucket ("Phase 1/Phase 2", "Phase 2/Phase 3"). Plus a "Not Applicable" bucket (`NA`, interventional non-drug trials) and a "No phase (observational / expanded access)" bucket (`phases` key absent). | **Yes** |
| D9.2 | Phase, `phase_mode: split` (option) | A trial counts in **each** of its phases. | No |
| D9.3 | **Drugs, conditions, countries, intervention types, collaborators, sites, investigators, age groups** | A trial counts **once per distinct value**. Duplicates within one trial are removed first (e.g. 37 US sites -> counted once for "United States"). | **No** |
| D9.4 | Single-valued dimensions (status, study type, lead sponsor, lead sponsor class, start year, allocation, primary purpose, results reported, ...) | One trial = one bucket. | **Yes** |
| D9.5 | **Missing values** | Not silently dropped (details in Q10). | n/a |
| D9.6 | **Networks** | **Node weight** = number of distinct trials containing that node. **Edge weight** = number of distinct trials containing both endpoints. Self-loops are removed (drug ↔ drug). | n/a |
| D9.7 | **Comparison groups** | Groups are separate searches. A trial that matches several groups (e.g. uses both pembrolizumab and nivolumab) counts in **each** group. `meta.group_overlap` reports the overlap count per pair of groups. | n/a |
| D9.8 | **Enrollment measures with a multi-valued dimension** | A trial's full enrollment is attributed to every bucket it belongs to. To avoid misleading readers, the measure is labelled accordingly (e.g. "participants in trials with sites in X", not "participants in X"), and `meta` explains it. ESTIMATED vs ACTUAL enrollment is reported. | No |

**As built (2026-10-25)** ([`aggregate.py`](../../backend/app/pipeline/aggregate.py), [`networks.py`](../../backend/app/pipeline/networks.py), [`charts.py`](../../backend/app/pipeline/charts.py)): D9.1-D9.5 and D9.7 are as designed. Two differences:
- **D9.6:** a node's weight counts only the trials where the entity has at least one link in the network. In a drug co-occurrence network, a trial with a single drug adds to no node. `meta.network.trials_without_links` reports how many trials that leaves out. The counting-rule sentence ("distinct trials with that entity") doesn't say this.
- **D9.8 is only partly built.** A trial's full enrollment does count in every bucket it belongs to, but the measure keeps its plain label ("Total enrollment"), `meta` doesn't explain the attribution, and ESTIMATED vs ACTUAL enrollment is not reported per bucket.
- The `distinct_count` measure ([Q4a](04a-plan-schema.md)) is never additive.

## Frontend contract

- **`meta.additive: true | false`** tells the renderer whether bars/series add up to the total. It decides whether percentages-of-total, stacking or pie-style views are valid.
- `meta.unique_trials` always gives the number of **distinct trials** behind the chart, which differs from the sum of bars when `additive` is false.
- `meta.counting_rule` is a short human-readable sentence (e.g. "Each trial is counted once per country where it has at least one site.").

## Requirement links

P3-10 (render metadata: grouping choices), P3-11 (assumptions), P7-3 (real-world data), P7-12/P7-13 (unambiguous, frontend-friendly output), P5 (citations: each bucket's trials are exactly the counted ones).
