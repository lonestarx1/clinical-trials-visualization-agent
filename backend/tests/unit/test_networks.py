"""Network graphs (design Q13), over the 8 recorded studies. Expected values worked out by hand:

Drugs per trial (DRUG/BIOLOGICAL interventions, MeSH-anchored, placebo skipped):
  NCT02648477 anastrozole, doxorubicin, exemestane, letrozole, pembrolizumab   (City of Hope)
  NCT07886905 dabrafenib, trametinib, pembrolizumab                            (WashU)
  NCT02506153 ipilimumab, pembrolizumab, interferon alpha-2                    (NCI)
  NCT04135092 individual patient tcr transduced pbl, cyclophosphamide,
              fludarabine, aldesleukin, pembrolizumab                          (NIH CC)
  NCT05894447 naptumomab estafenatox, pembrolizumab, obinutuzumab              (Weill Cornell)
  NCT03724851 vactosertib (1 drug)   NCT05834413 1 drug (other is placebo)   NCT04975932 none

Co-occurrence: 5 trials with >= 2 drugs, 15 drugs, 10+3+3+10+3 = 29 pairs (all distinct).
"""

from typing import Any

import pytest

from app.pipeline.charts import ChartResult, build_chart
from app.pipeline.citations import verify_citations
from app.schemas.plan import QueryPlan
from tests.support.samples import load_sample, sample_names

STUDIES = [load_sample(n) for n in sample_names()]
BY_ID = {s["protocolSection"]["identificationModule"]["nctId"]: s for s in STUDIES}


def network(**overrides: Any) -> ChartResult:
    base: dict[str, Any] = {
        "scope": "in_scope",
        "intent": "network",
        "chart_type": "network_graph",
        "dimension": "drug",
    }
    return build_chart(QueryPlan.model_validate(base | overrides), [(None, STUDIES)], now_year=2026)


def nodes(result: ChartResult) -> dict[str, dict[str, Any]]:
    return {n["id"]: n for n in result.visualization.data["nodes"]}  # type: ignore[call-overload]


def edges(result: ChartResult) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        tuple(sorted((e["source"], e["target"]))): e  # type: ignore[misc]
        for e in result.visualization.data["edges"]
    }  # type: ignore[call-overload]


def test_drug_co_occurrence() -> None:
    result = network()
    assert result.visualization.type == "network_graph"
    n, e = nodes(result), edges(result)
    assert len(n) == 15 and len(e) == 29
    pembro = n["drug:pembrolizumab"]
    assert (pembro["label"], pembro["weight"], pembro["degree"], pembro["type"]) == (
        "pembrolizumab",
        5,
        14,
        "drug",
    )
    assert all(edge["weight"] == 1 for edge in e.values())
    assert e[("drug:anastrozole", "drug:pembrolizumab")]["jaccard"] == pytest.approx(0.2)
    assert e[("drug:dabrafenib", "drug:trametinib")]["jaccard"] == pytest.approx(1.0)
    assert result.meta.unique_trials == 5


def test_network_meta_reports_pruning_and_the_algorithm() -> None:
    meta = network().meta.network
    assert meta is not None
    assert (meta["nodes_before"], meta["edges_before"], meta["nodes"], meta["edges"]) == (
        15,
        29,
        15,
        29,
    )
    assert meta["min_edge_weight"] == 1
    assert meta["trials_without_links"] == 3
    assert "modularity" in meta["community_algorithm"]


def test_query_entity_is_flagged_and_can_be_hidden() -> None:
    flagged = network(filters={"drugs": ["Pembrolizumab"]})
    assert nodes(flagged)["drug:pembrolizumab"]["is_query_entity"] is True
    assert nodes(flagged)["drug:dabrafenib"]["is_query_entity"] is False

    hidden = network(filters={"drugs": ["Pembrolizumab"]}, options={"hide_query_entity": True})
    assert "drug:pembrolizumab" not in nodes(hidden)
    assert (len(nodes(hidden)), len(edges(hidden))) == (14, 15)


@pytest.mark.parametrize("term", ["Keytruda", "MK-3475", "lambrolizumab"])
def test_query_entity_is_found_by_any_name_its_records_list(term: str) -> None:
    """The records list pembrolizumab's other names (Keytruda, MK-3475, Lambrolizumab), and
    the API matches them; the node is keyed "pembrolizumab", the MeSH term."""
    flagged = network(filters={"drugs": [term]})
    assert [n for n, v in nodes(flagged).items() if v["is_query_entity"]] == ["drug:pembrolizumab"]
    hidden = network(filters={"drugs": [term]}, options={"hide_query_entity": True})
    assert "drug:pembrolizumab" not in nodes(hidden)
    assert (len(nodes(hidden)), len(edges(hidden))) == (14, 15)
    assert flagged.meta.network["query_entities"] == [  # type: ignore[index]
        {"term": term, "node": "drug:pembrolizumab", "matched_by": "name"}
    ]


def test_query_entity_named_nowhere_is_the_entity_in_most_trials() -> None:
    """No record calls it "Pembro", but every trial matched the search: pembrolizumab is in 5
    of the 7 trials with a drug, and no other drug is in more than 1, so it's the query entity."""
    flagged = network(filters={"drugs": ["Pembro"]})
    assert [n for n, v in nodes(flagged).items() if v["is_query_entity"]] == ["drug:pembrolizumab"]
    assert flagged.meta.network["query_entities"] == [  # type: ignore[index]
        {"term": "Pembro", "node": "drug:pembrolizumab", "matched_by": "in most trials"}
    ]


def test_no_entity_is_guessed_when_none_is_in_most_trials() -> None:
    """Breast Neoplasms is in 1 of the 7 trials with a MeSH condition: not the query entity."""
    result = network(filters={"conditions": ["breast cancer"]}, dimension_2="condition")
    assert not any(v["is_query_entity"] for v in nodes(result).values())
    assert result.meta.network["query_entities"] == [  # type: ignore[index]
        {"term": "breast cancer", "node": None, "matched_by": None}
    ]


def test_communities_are_deterministic() -> None:
    first = {k: v["community"] for k, v in nodes(network()).items()}
    second = {k: v["community"] for k, v in nodes(network()).items()}
    assert first == second
    assert all(isinstance(c, int) for c in first.values())


def test_sponsor_drug_bipartite_network() -> None:
    result = network(dimension="sponsor", dimension_2="drug")
    n, e = nodes(result), edges(result)
    # 7 sponsors with a drug (Zhongda has none, so it has no edge and is dropped) + 17 drugs
    assert (len(n), len(e)) == (24, 21)
    city = n["sponsor:city of hope medical center"]
    assert (city["type"], city["weight"], city["degree"]) == ("sponsor", 1, 5)
    link = e[("drug:pembrolizumab", "sponsor:national cancer institute (nci)")]
    assert (link["weight"], link["jaccard"]) == (1, pytest.approx(0.2))
    assert result.visualization.encoding["node_color"].field == "type"


def test_edge_citations_cite_both_ends() -> None:
    result = network(dimension="sponsor", dimension_2="drug")
    link = edges(result)[("drug:dabrafenib", "sponsor:washington university school of medicine")]
    [citation] = link["citations"]
    fields = [ev["field"] for ev in citation["evidence"]]
    assert "protocolSection.sponsorCollaboratorsModule.leadSponsor.name" in fields
    assert any(f.startswith("derivedSection.interventionBrowseModule.meshes") for f in fields)
    verify_citations(result.visualization, BY_ID)


def test_edge_metric_option_changes_the_width_channel() -> None:
    assert network().visualization.encoding["edge_width"].field == "weight"
    assert (
        network(options={"edge_metric": "jaccard"}).visualization.encoding["edge_width"].field
        == "jaccard"
    )


def test_top_n_per_type_and_min_edge_weight() -> None:
    result = network(options={"top_n": 3})
    assert len(nodes(result)) <= 3
    assert "drug:pembrolizumab" in nodes(result)
    raised = network(options={"network_min_edge_weight": 2})
    assert len(edges(raised)) == 0 and len(nodes(raised)) == 0


def test_investigator_site_links_only_within_the_same_site() -> None:
    result = network(dimension="investigator", dimension_2="site")
    n, e = nodes(result), edges(result)
    # NCT07886905 lists 21 site investigators at its one site
    assert (len(n), len(e)) == (22, 21)
    assert result.meta.network is not None and result.meta.network["trials_with_data"] == 1
