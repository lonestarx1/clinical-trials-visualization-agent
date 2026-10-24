"""Raw study -> grouped values with exact evidence (design Q9, Q10, Q11, Q14).

Expected values were read by hand from the sample JSON (jq), not from this code.
"""

import copy
from datetime import date

import pytest

from app.pipeline.extract import Evidence, extract, extract_number, value_at
from tests.support.samples import load_sample

DESIGN = "protocolSection.designModule"
STATUS = "protocolSection.statusModule"


def keys(study_name: str, dimension: str, **options: str) -> list[str]:
    return [v.key for v in extract(load_sample(study_name), dimension, **options)]


def test_value_at_follows_dotted_and_indexed_paths() -> None:
    study = load_sample("multi_phase")
    assert value_at(study, f"{DESIGN}.phases[1]") == "PHASE2"
    assert value_at(study, f"{DESIGN}.nothing.here") is None
    assert value_at(study, f"{DESIGN}.phases[9]") is None


def test_combined_phase_bucket_cites_both_phases() -> None:
    [value] = extract(load_sample("multi_phase"), "phase")
    assert (value.key, value.label) == ("PHASE1/PHASE2", "Phase 1/Phase 2")
    assert value.evidence == (
        Evidence(f"{DESIGN}.phases[0]", "PHASE1"),
        Evidence(f"{DESIGN}.phases[1]", "PHASE2"),
    )


def test_split_phase_mode_gives_one_value_per_phase() -> None:
    assert keys("multi_phase", "phase", phase_mode="split") == ["PHASE1", "PHASE2"]


@pytest.mark.parametrize(
    ("sample", "study_type"),
    [("observational", "OBSERVATIONAL"), ("missing_start", "EXPANDED_ACCESS")],
)
def test_trials_without_phases_get_the_no_phase_bucket(sample: str, study_type: str) -> None:
    [value] = extract(load_sample(sample), "phase")
    assert value.key == "NO_PHASE"
    assert value.label == "No phase (observational / expanded access)"
    assert value.evidence == (Evidence(f"{DESIGN}.studyType", study_type),)


def test_not_applicable_phase() -> None:
    assert keys("placebo", "phase") == ["NA"]


def test_single_valued_enums() -> None:
    [status] = extract(load_sample("combo"), "status")
    assert (status.key, status.label) == ("COMPLETED", "Completed")
    assert status.evidence == (Evidence(f"{STATUS}.overallStatus", "COMPLETED"),)
    assert keys("multi_phase", "sponsor_class") == ["INDUSTRY"]


def test_multi_valued_enums_are_distinct_and_cite_the_first_occurrence() -> None:
    values = extract(load_sample("combo"), "intervention_type")
    assert [v.key for v in values] == ["DRUG", "OTHER", "BIOLOGICAL"]
    path = "protocolSection.armsInterventionsModule.interventions"
    assert [v.evidence for v in values] == [
        (Evidence(f"{path}[0].type", "DRUG"),),
        (Evidence(f"{path}[3].type", "OTHER"),),
        (Evidence(f"{path}[5].type", "BIOLOGICAL"),),
    ]


def test_booleans() -> None:
    [value] = extract(load_sample("combo"), "has_results")
    assert (value.key, value.label) == ("true", "Yes")
    assert value.evidence == (Evidence("hasResults", True),)
    assert keys("combo", "healthy_volunteers") == ["false"]


def test_countries_once_per_trial() -> None:
    assert sorted(keys("many_locations", "country")) == ["Canada", "Ireland", "United States"]
    assert keys("missing_start", "country") == []


def test_us_states_only_for_us_sites() -> None:
    assert len(keys("many_locations", "us_state")) == 50
    assert keys("future_start", "us_state") == ["Missouri"]
    assert keys("multi_phase", "us_state") == []


def test_start_year_with_estimated_and_partial_dates() -> None:
    [actual] = extract(load_sample("combo"), "start_year")
    assert (actual.key, actual.estimated) == ("2016", False)
    assert actual.evidence == (Evidence(f"{STATUS}.startDateStruct.date", "2016-03-28"),)
    [partial] = extract(load_sample("partial_date"), "start_year")
    assert (partial.key, partial.estimated) == ("2023", True)
    assert keys("missing_start", "start_year") == []


def test_first_posted_year() -> None:
    assert keys("combo", "first_posted_year") == ["2016"]


def test_sponsor_names_are_case_folded_keys_with_raw_labels() -> None:
    [sponsor] = extract(load_sample("combo"), "sponsor")
    assert (sponsor.key, sponsor.label) == (
        "city of hope medical center",
        "City of Hope Medical Center",
    )
    assert keys("combo", "collaborator") == [
        "national cancer institute (nci)",
        "merck sharp & dohme llc",
    ]


def test_drugs_group_by_mesh_term() -> None:
    values = extract(load_sample("combo"), "drug")
    assert [v.key for v in values] == [
        "anastrozole",
        "doxorubicin",
        "exemestane",
        "letrozole",
        "pembrolizumab",
    ]
    mesh = "derivedSection.interventionBrowseModule.meshes"
    assert values[2].evidence[0] == Evidence(f"{mesh}[2].term", "exemestane")


def test_drugs_fall_back_to_cleaned_names_without_mesh_and_skip_placebo() -> None:
    study = copy.deepcopy(load_sample("placebo"))
    del study["derivedSection"]["interventionBrowseModule"]
    values = extract(study, "drug")
    assert [v.key for v in values] == ["chemotherapy plus tcm 1&icis plustcm2"]
    path = "protocolSection.armsInterventionsModule.interventions"
    assert values[0].evidence == (
        Evidence(f"{path}[0].name", "chemotherapy plus TCM 1&ICIs plusTCM2"),
    )


def test_trials_without_drug_interventions_have_no_drugs() -> None:
    assert keys("observational", "drug") == []


def test_conditions_by_mesh_or_raw() -> None:
    assert keys("combo", "condition") == ["breast neoplasms", "triple negative breast neoplasms"]
    raw = keys("combo", "condition", condition_source="raw")
    assert len(raw) == 7
    assert raw[-1] == "triple-negative breast carcinoma"


def test_sites_and_site_investigators() -> None:
    [site] = extract(load_sample("future_start"), "site")
    assert site.label == "Washington University School of Medicine, St Louis, United States"
    investigators = extract(load_sample("future_start"), "investigator")
    assert len(investigators) == 21
    assert investigators[0].key == "nikhil rammohan"
    assert investigators[0].label == "Nikhil Rammohan"


def test_numbers() -> None:
    enrollment = extract_number(load_sample("combo"), "enrollment")
    assert enrollment is not None
    assert (enrollment.value, enrollment.estimated) == (30, False)
    assert extract_number(load_sample("partial_date"), "enrollment").value == 0  # type: ignore[union-attr]
    assert extract_number(load_sample("missing_start"), "enrollment") is None

    duration = extract_number(load_sample("combo"), "duration_months")
    expected = (date(2023, 12, 30) - date(2016, 3, 28)).days / 30.4375
    assert duration is not None and duration.value == pytest.approx(expected, abs=0.05)

    assert extract_number(load_sample("many_locations"), "site_count").value == 576  # type: ignore[union-attr]
    assert extract_number(load_sample("missing_start"), "site_count").value == 0  # type: ignore[union-attr]
