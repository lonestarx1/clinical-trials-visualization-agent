"""Network graphs (design Q13): nodes = entities, edges = trials that link them.

Node weight = distinct trials containing the entity; edge weight = distinct
trials containing both, plus Jaccard (shared / either) for how specific a link
is. Pruning is deterministic and recorded in meta.network.
"""

from collections import Counter, defaultdict
from collections.abc import Sequence
from itertools import combinations
from typing import Any

import networkx as nx

from app.pipeline.aggregate import nct_id
from app.pipeline.citations import sample_citations
from app.pipeline.extract import Evidence, Value, extract, normalise_name, site_investigator_pairs
from app.registry import DIMENSIONS, Dimension
from app.schemas.plan import QueryPlan
from app.schemas.response import Channel, Visualization

MAX_EDGES = 150
TOP_PER_TYPE, TOP_CO_OCCURRENCE = 25, 40
COMMUNITY_ALGORITHM = "greedy modularity (networkx), weighted by edge weight"
QUERY_TERMS = {
    "drug": "drugs",
    "condition": "conditions",
    "sponsor": "sponsors",
    "collaborator": "sponsors",
    "country": "countries",
}


def _node_id(dim: Dimension, value: Value) -> str:
    return f"{dim.key}:{value.key}"


def _pairs(
    study: dict[str, Any], plan: QueryPlan, a: Dimension, b: Dimension | None
) -> tuple[list[tuple[tuple[Dimension, Value], tuple[Dimension, Value]]], bool]:
    """Linked value pairs in one trial, and whether the trial had any data for the network."""
    opts = {
        "phase_mode": plan.options.phase_mode or "combined",
        "condition_source": plan.options.condition_source or "mesh",
    }
    if b is None:  # co-occurrence: trials with >= 2 distinct values
        values = extract(study, a.key, **opts)  # type: ignore[arg-type]
        return [((a, x), (a, y)) for x, y in combinations(values, 2)], bool(values)
    if {a.key, b.key} == {"investigator", "site"}:
        found = site_investigator_pairs(study)
        inv, site = DIMENSIONS["investigator"], DIMENSIONS["site"]
        pairs = [((inv, i), (site, s)) for i, s in found]
        return (pairs if a.key == "investigator" else [(y, x) for x, y in pairs]), bool(found)
    left = extract(study, a.key, **opts)  # type: ignore[arg-type]
    right = extract(study, b.key, **opts)  # type: ignore[arg-type]
    return [
        ((a, x), (b, y)) for x in left for y in right if (a.key, x.key) != (b.key, y.key)
    ], bool(left or right)


def build_network(
    plan: QueryPlan,
    studies: Sequence[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    limit: int,
) -> tuple[Visualization, dict[str, Any], int]:
    """(visualization, meta.network, unique trials linked)."""
    assert plan.dimension is not None
    a = DIMENSIONS[plan.dimension]
    b = (
        DIMENSIONS[plan.dimension_2]
        if plan.dimension_2 and plan.dimension_2 != plan.dimension
        else None
    )
    opts = plan.options

    node_trials: dict[str, dict[str, tuple[Evidence, ...]]] = defaultdict(dict)
    node_labels: dict[str, Counter[str]] = defaultdict(Counter)
    node_types: dict[str, str] = {}
    edge_trials: dict[tuple[str, str], dict[str, tuple[Evidence, ...]]] = defaultdict(dict)
    with_data, linked = set(), set()

    for study in studies:
        trial = nct_id(study)
        pairs, has_data = _pairs(study, plan, a, b)
        if has_data:
            with_data.add(trial)
        for (dx, x), (dy, y) in pairs:
            ix, iy = _node_id(dx, x), _node_id(dy, y)
            if ix == iy:
                continue
            for dim, value, node in ((dx, x, ix), (dy, y, iy)):
                node_trials[node][trial] = value.evidence
                node_labels[node][value.label] += 1
                node_types[node] = dim.key
            key = (ix, iy) if ix < iy else (iy, ix)
            edge_trials[key][trial] = x.evidence + y.evidence
            linked.add(trial)

    # The queried entity links to everything; flag it, or hide it on request (D13.1).
    terms: set[str] = set()
    for dim in [d for d in (a, b) if d is not None]:
        if dim.key in QUERY_TERMS:
            terms |= {
                f"{dim.key}:{normalise_name(t)}"
                for t in getattr(plan.filters, QUERY_TERMS[dim.key])
            }
    candidates = [n for n in node_trials if not (opts.hide_query_entity and n in terms)]
    candidate_edges = {
        k: v for k, v in edge_trials.items() if k[0] in candidates and k[1] in candidates
    }
    nodes_before, edges_before = len(candidates), len(candidate_edges)

    def label(node: str) -> str:
        return min(node_labels[node].items(), key=lambda kv: (-kv[1], kv[0]))[0]

    top_n = opts.top_n or (TOP_CO_OCCURRENCE if b is None else TOP_PER_TYPE)
    kept: set[str] = set()
    for node_type in sorted({node_types[n] for n in candidates}):
        ranked = sorted(
            (n for n in candidates if node_types[n] == node_type),
            key=lambda n: (-len(node_trials[n]), label(n).casefold()),
        )
        kept |= set(ranked[:top_n])
    edges = {k: v for k, v in candidate_edges.items() if k[0] in kept and k[1] in kept}
    threshold = opts.network_min_edge_weight or 1
    while sum(1 for v in edges.values() if len(v) >= threshold) > MAX_EDGES:
        threshold += 1
    edges = {k: v for k, v in edges.items() if len(v) >= threshold}
    final_nodes = sorted({n for k in edges for n in k})

    graph: nx.Graph[str] = nx.Graph()
    graph.add_nodes_from(final_nodes)
    graph.add_weighted_edges_from((s, t, len(v)) for (s, t), v in sorted(edges.items()))
    communities = sorted(
        nx.community.greedy_modularity_communities(graph, weight="weight") if edges else [],
        key=lambda c: (-len(c), min(c)),
    )
    community = {n: i for i, members in enumerate(communities) for n in members}

    node_rows = [
        {
            "key": n,
            "id": n,
            "label": label(n),
            "type": node_types[n],
            "weight": len(node_trials[n]),
            "degree": graph.degree(n),
            "community": community.get(n, 0),
            "is_query_entity": n in terms,
        }
        | sample_citations(node_trials[n], by_id, limit)
        for n in sorted(final_nodes, key=lambda n: (node_types[n], -len(node_trials[n]), label(n)))
    ]
    edge_rows = [
        {
            "key": f"{s}|{t}",
            "source": s,
            "target": t,
            "weight": len(v),
            "jaccard": round(len(v) / len(set(node_trials[s]) | set(node_trials[t])), 4),
        }
        | sample_citations(v, by_id, limit)
        for (s, t), v in sorted(edges.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    ]

    color = "community" if b is None else "type"
    width = "jaccard" if opts.edge_metric == "jaccard" else "weight"
    encoding = {
        "node_id": Channel(field="id", type="nominal", label="Entity"),
        "node_label": Channel(field="label", type="nominal", label="Name"),
        "node_size": Channel(field="weight", type="quantitative", label="Trials", unit="trials"),
        "node_color": Channel(field=color, type="nominal", label=color.capitalize()),
        "edge_source": Channel(field="source", type="nominal", label="From"),
        "edge_target": Channel(field="target", type="nominal", label="To"),
        "edge_width": Channel(
            field=width,
            type="quantitative",
            label="Shared trials" if width == "weight" else "Jaccard similarity",
            unit="trials" if width == "weight" else None,
        ),
    }
    names = f"{a.label} - {b.label}" if b else f"{a.label} co-occurrence"
    viz = Visualization(
        type="network_graph",
        title=f"{names} network",
        summary=f"{len(final_nodes)} entities and {len(edges)} links across {len(linked)} trials.",
        encoding=encoding,
        data={"nodes": node_rows, "edges": edge_rows},
    )
    meta = {
        "nodes_before": nodes_before,
        "edges_before": edges_before,
        "nodes": len(final_nodes),
        "edges": len(edges),
        "min_edge_weight": threshold,
        "top_n_per_type": top_n,
        "trials_with_data": len(with_data),
        "trials_without_links": len(studies) - len(linked),
        "community_algorithm": COMMUNITY_ALGORITHM,
    }
    return viz, meta, len(linked)
