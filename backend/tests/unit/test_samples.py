from tests.support.samples import load_sample, sample_names

EXPECTED = {
    "combo": "NCT02648477",
    "future_start": "NCT07886905",
    "many_locations": "NCT02506153",
    "missing_start": "NCT04135092",
    "multi_phase": "NCT03724851",
    "observational": "NCT04975932",
    "partial_date": "NCT05894447",
    "placebo": "NCT05834413",
}


def test_all_probe_samples_are_available() -> None:
    assert set(sample_names()) == set(EXPECTED)


def test_each_sample_is_the_study_its_file_names() -> None:
    for name, nct_id in EXPECTED.items():
        study = load_sample(name)
        assert study["protocolSection"]["identificationModule"]["nctId"] == nct_id
