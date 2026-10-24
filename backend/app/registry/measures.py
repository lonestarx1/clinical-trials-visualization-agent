from dataclasses import dataclass


@dataclass(frozen=True)
class Measure:
    key: str
    label: str
    unit: str
    fields: tuple[str, ...]  # API pieces needed to compute it


MEASURES: dict[str, Measure] = {
    m.key: m
    for m in [
        Measure("trial_count", "Number of trials", "trials", ()),
        Measure(
            "total_enrollment",
            "Total enrollment",
            "participants",
            ("EnrollmentCount", "EnrollmentType"),
        ),
        Measure(
            "median_enrollment",
            "Median enrollment",
            "participants",
            ("EnrollmentCount", "EnrollmentType"),
        ),
    ]
}
