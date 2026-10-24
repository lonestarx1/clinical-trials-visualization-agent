"""The registry must match the real API: every piece, path and enum value is checked
against the metadata saved from /studies/metadata and /studies/enums."""

import json
from pathlib import Path

import pytest

from app.registry import DIMENSIONS, MEASURES, ChartType, DimensionKind, Intent
from app.registry import enums as e

REFERENCE = Path(__file__).resolve().parents[3] / "docs" / "api" / "reference"


def _api_pieces() -> dict[str, str]:
    """piece -> dotted JSON path, for every field in the study data model."""
    pieces: dict[str, str] = {}

    def walk(nodes: list[dict], path: str) -> None:
        for node in nodes:
            p = f"{path}.{node['name']}" if path else node["name"]
            if node.get("piece"):
                pieces[node["piece"]] = p
            walk(node.get("children", []), p)

    walk(json.loads((REFERENCE / "studies-metadata.json").read_text()), "")
    return pieces


API_PIECES = _api_pieces()
API_ENUMS = {
    item["type"]: [v["value"] for v in item["values"]]
    for item in json.loads((REFERENCE / "studies-enums.json").read_text())
}


@pytest.mark.parametrize(
    ("ours", "api_name"),
    [
        (e.Phase, "Phase"),
        (e.Status, "Status"),
        (e.StudyType, "StudyType"),
        (e.AgencyClass, "AgencyClass"),
        (e.InterventionType, "InterventionType"),
        (e.StandardAge, "StandardAge"),
        (e.Sex, "Sex"),
        (e.Allocation, "DesignAllocation"),
        (e.Masking, "DesignMasking"),
        (e.PrimaryPurpose, "PrimaryPurpose"),
    ],
)
def test_enums_match_the_api(ours: type[e.LabelledEnum], api_name: str) -> None:
    assert [m.value for m in ours] == API_ENUMS[api_name]
    assert all(m.label for m in ours)


def test_every_dimension_uses_real_api_pieces() -> None:
    for dim in DIMENSIONS.values():
        assert dim.filter_piece is None or dim.filter_piece in API_PIECES, dim.key
        for piece in dim.fields:
            assert piece in API_PIECES, f"{dim.key}: unknown piece {piece}"


def test_every_measure_uses_real_api_pieces() -> None:
    for measure in MEASURES.values():
        for piece in measure.fields:
            assert piece in API_PIECES, f"{measure.key}: unknown piece {piece}"


def test_dimension_keys_used_by_the_appendix_questions_exist() -> None:
    needed = {
        "start_year",
        "phase",
        "intervention_type",
        "sponsor_class",
        "country",
        "sponsor",
        "drug",
    }
    assert needed <= DIMENSIONS.keys()


def test_beyond_appendix_dimensions_exist() -> None:
    """Design Q1: nine dimensions added beyond the appendix."""
    added = {
        "has_results",
        "age_group",
        "sex",
        "healthy_volunteers",
        "allocation",
        "masking",
        "primary_purpose",
        "us_state",
        "first_posted_year",
    }
    assert added <= DIMENSIONS.keys()


def test_bounded_dimensions_list_their_values() -> None:
    """Strategy S2 (count per bucket) needs a known, finite value list."""
    for dim in DIMENSIONS.values():
        if dim.kind is DimensionKind.CATEGORICAL and dim.enum is not None:
            assert dim.filter_piece, dim.key


def test_multi_valued_flags_follow_the_counting_rules() -> None:
    """Design Q9: these are counted once per distinct value, so bars don't add up."""
    multi = {
        "drug",
        "condition",
        "country",
        "intervention_type",
        "collaborator",
        "site",
        "investigator",
        "age_group",
        "us_state",
    }
    for key in multi:
        assert DIMENSIONS[key].multi_valued, key
    for key in ("status", "study_type", "sponsor", "sponsor_class", "start_year"):
        assert not DIMENSIONS[key].multi_valued, key


def test_every_dimension_states_its_counting_rule() -> None:
    for dim in DIMENSIONS.values():
        assert dim.counting_rule.endswith("."), dim.key


def test_numeric_dimensions_for_histograms_and_scatter() -> None:
    numeric = {k for k, d in DIMENSIONS.items() if d.kind is DimensionKind.NUMERIC}
    assert {"enrollment", "duration_months", "site_count"} <= numeric


def test_measures_and_chart_types() -> None:
    assert set(MEASURES) == {
        "trial_count",
        "total_enrollment",
        "median_enrollment",
        "distinct_count",
    }
    assert {c.value for c in ChartType} == {
        "bar_chart",
        "grouped_bar_chart",
        "time_series",
        "histogram",
        "scatter_plot",
        "network_graph",
        "metric",
    }
    assert len(Intent) == 9
