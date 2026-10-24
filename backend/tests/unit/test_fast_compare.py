"""Shadow runs (design Q22): a fast answer compared value by value with the live one."""

from typing import Any

from app.mirror.fast import differences


def bars(*points: tuple[str, int, int]) -> dict[str, Any]:
    return {"data": [{"key": k, "value": v, "citation_count": c} for k, v, c in points]}


def test_equal_charts_have_no_differences() -> None:
    chart = bars(("PHASE2", 5, 5), ("PHASE3", 2, 2))
    assert differences(chart, bars(("PHASE3", 2, 2), ("PHASE2", 5, 5))) == []


def test_a_different_value_or_bucket_is_reported() -> None:
    fast = bars(("PHASE2", 5, 5), ("PHASE3", 2, 2))
    live = bars(("PHASE2", 6, 6), ("PHASE1", 1, 1))
    assert differences(fast, live) == [
        "PHASE1: fast None, live (1, 1)",
        "PHASE2: fast (5, 5), live (6, 6)",
        "PHASE3: fast (2, 2), live None",
    ]


def test_networks_compare_nodes_and_edges() -> None:
    node = {"key": "drug:a", "value": 3, "citation_count": 3}
    edge = {"key": "drug:a|drug:b", "value": 1, "citation_count": 1}
    fast = {"data": {"nodes": [node], "edges": [edge]}}
    live = {"data": {"nodes": [node], "edges": [edge | {"value": 2}]}}
    assert differences(fast, live) == ["drug:a|drug:b: fast (1, 1), live (2, 1)"]
