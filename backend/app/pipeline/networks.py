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

from app.ctgov.countries import resolve_country
from app.pipeline.aggregate import nct_id
from app.pipeline.citations import sample_citations
from app.pipeline.extract import (
    Evidence,
    Value,
    clean_drug_name,
    extract,
    normalise_name,
    site_investigator_pairs,
)
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
) -> tuple[list[tuple[tuple[Dimension, Value], tuple[Dimension, Value]]], set[str]]:
    """Linked value pairs in one trial, and the network dimensions it has any value for."""
    opts = {
        "phase_mode": plan.options.phase_mode or "combined",
        "condition_source": plan.options.condition_source or "mesh",
    }
    if b is None:  # co-occurrence: trials with >= 2 distinct values
        values = extract(study, a.key, **opts)  # type: ignore[arg-type]
        return [((a, x), (a, y)) for x, y in combinations(values, 2)], {a.key} if values else set()
    if {a.key, b.key} == {"investigator", "site"}:
        found = site_investigator_pairs(study)
        inv, site = DIMENSIONS["investigator"], DIMENSIONS["site"]
        pairs = [((inv, i), (site, s)) for i, s in found]
        ordered = pairs if a.key == "investigator" else [(y, x) for x, y in pairs]
        return ordered, {"investigator", "site"} if found else set()
    left = extract(study, a.key, **opts)  # type: ignore[arg-type]
    right = extract(study, b.key, **opts)  # type: ignore[arg-type]
    pairs = [((a, x), (b, y)) for x in left for y in right if (a.key, x.key) != (b.key, y.key)]
    return pairs, {d.key for d, values in ((a, left), (b, right)) if values}


def _term_names(dimension: str, term: str) -> set[str]:
    """The normalised names a search term can have as a node of this dimension."""
    names = {normalise_name(term)}
    if dimension == "drug" and (cleaned := clean_drug_name(term)):
        names.add(cleaned)
    if dimension == "country":
        names.add(normalise_name(resolve_country(term)[0]))
    return names


def _query_entities(
    plan: QueryPlan,
    dims: Sequence[Dimension],
    names: dict[str, set[str]],
    trials: dict[str, dict[str, tuple[Evidence, ...]]],
    trials_with: Counter[str],
) -> tuple[list[dict[str, Any]], set[str]]:
    """The node each search term on a network dimension is, and how it was found (D13.1).

    Nodes are keyed by MeSH terms and cleaned API names, not the user's words, so a term is
    first matched against every name the records give a node (a drug's other names included:
    "Keytruda" is pembrolizumab). A term no record uses still matched every trial through the
    API's synonyms, so if one node of that type is in more than half the trials with a value
    for it, and in more than any other node, it is that node. Otherwise none is flagged.
    """
    found: list[dict[str, Any]] = []
    flagged: set[str] = set()
    for dim in dims:
        if dim.key not in QUERY_TERMS:
            continue
        same_type = sorted(n for n in trials if n.startswith(f"{dim.key}:"))
        for term in getattr(plan.filters, QUERY_TERMS[dim.key]):
            wanted = _term_names(dim.key, term)
            node = next((n for n in same_type if names[n] & wanted), None)
            how: str | None = "name" if node else None
            if node is None:
                ranked = sorted(same_type, key=lambda n: -len(trials[n]))
                top = len(trials[ranked[0]]) if ranked else 0
                runner_up = len(trials[ranked[1]]) if len(ranked) > 1 else 0
                if top * 2 > trials_with[dim.key] and top > runner_up:
                    node, how = ranked[0], "in most trials"
            found.append({"term": term, "node": node, "matched_by": how})
            if node:
                flagged.add(node)
    return found, flagged


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
    node_names: dict[str, set[str]] = defaultdict(set)  # every name the records give a node
    trials_with: Counter[str] = Counter()  # dimension -> trials with any value for it
    node_types: dict[str, str] = {}
    edge_trials: dict[tuple[str, str], dict[str, tuple[Evidence, ...]]] = defaultdict(dict)
    with_data, linked = set(), set()

    for study in studies:
        trial = nct_id(study)
        pairs, dims_with_data = _pairs(study, plan, a, b)
        if dims_with_data:
            with_data.add(trial)
        trials_with.update(dims_with_data)
        for (dx, x), (dy, y) in pairs:
            ix, iy = _node_id(dx, x), _node_id(dy, y)
            if ix == iy:
                continue
            for dim, value, node in ((dx, x, ix), (dy, y, iy)):
                node_trials[node][trial] = value.evidence
                node_labels[node][value.label] += 1
                node_names[node] |= {value.key, normalise_name(value.label), *value.aliases}
                node_types[node] = dim.key
            key = (ix, iy) if ix < iy else (iy, ix)
            edge_trials[key][trial] = x.evidence + y.evidence
            linked.add(trial)

    # The queried entity links to everything; flag it, or hide it on request (D13.1).
    query_entities, terms = _query_entities(
        plan, [d for d in (a, b) if d is not None], node_names, node_trials, trials_with
    )
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
        "query_entities": query_entities,
    }
    return viz, meta, len(linked)
