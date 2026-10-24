# Design Q13: Meaningful network graphs

Status: **Decided** (2026-10-24)

Part 4 and Part 7 both single out "meaningful network graphs" as worth more points. This file defines what "meaningful" means for us.

## Network types

| Kind | Types | Edge means |
|---|---|---|
| **Bipartite** (two node types) | sponsor ↔ drug, condition ↔ drug, sponsor ↔ condition, investigator ↔ site, sponsor ↔ collaborator | At least one trial links the two entities |
| **Co-occurrence** (one node type) | drug ↔ drug | Both drugs appear in the same trial. Only trials with **>= 2 distinct drugs** (after placebo exclusion and normalisation, Q11) count. Self-loops are removed. |

Sponsor ↔ collaborator always uses both sponsor roles (Q7, D7.6). Other sponsor networks follow `sponsor_role`.

**Investigator ↔ site (found during the consistency review):**
- The edge uses **site-level** investigators: `locations[].contacts[]` with role `PRINCIPAL_INVESTIGATOR` or `SUB_INVESTIGATOR` (enum `ContactRole`), linked to **that** site (facility + city + country).
- Trial-level `overallOfficials` are **not** linked to every site, because that would invent links.
- Site contacts are sparse (often only listed for recruiting trials), so `meta` reports how many trials had any site-level investigator data, and the README lists this as a data limitation.

## Node and edge fields

| Element | Fields |
|---|---|
| Node | `id` (`<type>:<normalised key>`), `label` (most common raw spelling), `type`, `weight` (= distinct trials containing the node; as built, linked trials only, see below), `degree` (edges after pruning), `community`, `is_query_entity`, `citations` |
| Edge | `source`, `target`, `weight` (= distinct trials containing both), `jaccard` (= shared trials / trials containing either node), `citations` |

**Why Jaccard as well:** raw counts favour hubs. Carboplatin co-occurs with almost every chemo combination, so by count it looks linked to everything. Jaccard measures how **specific** a link is. Both values are sent: `encoding.edge_width` defaults to `weight`, and `edge_metric: count | jaccard` lets the user choose.

## Pruning (keep the graph readable)

| Step | Rule (defaults configurable via `options`) |
|---|---|
| 1 | Keep the **top N nodes per type** by weight (default **25**). For co-occurrence, top 40 drugs. |
| 2 | **Minimum edge weight** (default **1**, revised from 2 during implementation so small scopes keep their links), raised automatically until there are **<= 150 edges**. |
| 3 | Remove nodes left **without edges**. |
| 4 | Record in `meta.network`: nodes/edges **before and after** pruning, the final thresholds, and the counts of trials and links that were cut. |

The pruning is deterministic (ties broken by label), so the same data always gives the same graph.

## Extras

| # | Decision |
|---|---|
| D13.1 | **Highlight the queried entity.** In a pembrolizumab drug ↔ drug network, pembrolizumab links to everything. Its node gets `is_query_entity: true`, and `options.hide_query_entity: true` removes it (to show which drugs combine **with each other**). |
| D13.2 | **Communities:** a deterministic community-detection algorithm (e.g. greedy modularity / Louvain with a fixed seed) labels every node with a `community`, so the frontend can colour clusters (e.g. "chemotherapy combinations" vs "immunotherapy combinations"). The algorithm is named in `meta`. |
| D13.3 | **No layout coordinates.** Layout is the frontend's job (force-directed etc.). We send graph structure and weights only. |
| D13.4 | **Encoding hints:** node size = `weight`, node colour = `type` (bipartite) or `community` (co-occurrence), edge width = `weight` or `jaccard`. |

## As built (2026-10-25): two limits

- **Query-entity match is by name, so it can miss silently.** `is_query_entity` and `hide_query_entity` compare the filter's text, case-folded, with node keys, which are normalised MeSH terms for drugs and conditions (`app/pipeline/networks.py`, around line 101). "pembrolizumab" matches its node; "Keytruda" or "lung cancer" (MeSH "Lung Neoplasms") match nothing, so no node is flagged or hidden and nothing says so. Fix (code): map the filter through the same MeSH lookup, or flag nodes present in every trial, and add a note when nothing matched.
- **Node weight counts linked trials only.** A node's `weight`, and the Jaccard denominator, count the trials in which the node is part of at least one edge. For drug ↔ drug that is the stated rule (trials with >= 2 drugs). For two node types it means a sponsor's weight is its trials **with at least one drug**, not all its trials in scope. `meta.network.trials_without_links` reports how many trials gave no link.

## Requirement links

P4-2e, P4-4 (network graphs, meaningful), P5-1a (node/edge weight citations), P7-11 (richer visualisations), PA-8, PA-9 (appendix network questions).
