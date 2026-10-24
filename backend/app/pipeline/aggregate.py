"""Group trials into buckets for one dimension (design Q9, Q10).

Each bucket keeps, per trial, the evidence that put the trial there, so
citations are exactly the counted trials.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.pipeline.extract import (
    INTERVENTIONS,
    LOCATIONS,
    Evidence,
    Value,
    extract,
    value_at,
)
from app.registry import Dimension, DimensionKind
from app.schemas.plan import QueryPlan

NOT_REPORTED = "NOT_REPORTED"
NOT_REPORTED_LABEL = "Not reported"

# Where a missing value would have been, so a "Not reported" citation can be checked.
MISSING_PATHS = {
    "phase": "protocolSection.designModule.phases",
    "status": "protocolSection.statusModule.overallStatus",
    "study_type": "protocolSection.designModule.studyType",
    "sponsor_class": "protocolSection.sponsorCollaboratorsModule.leadSponsor.class",
    "intervention_type": INTERVENTIONS,
    "age_group": "protocolSection.eligibilityModule.stdAges",
    "sex": "protocolSection.eligibilityModule.sex",
    "healthy_volunteers": "protocolSection.eligibilityModule.healthyVolunteers",
    "allocation": "protocolSection.designModule.designInfo.allocation",
    "masking": "protocolSection.designModule.designInfo.maskingInfo.masking",
    "primary_purpose": "protocolSection.designModule.designInfo.primaryPurpose",
    "has_results": "hasResults",
    "country": LOCATIONS,
    "site": LOCATIONS,
    "sponsor": "protocolSection.sponsorCollaboratorsModule.leadSponsor.name",
    "collaborator": "protocolSection.sponsorCollaboratorsModule.collaborators",
    "condition": "derivedSection.conditionBrowseModule.meshes",
}

TIME_WORDS = {
    "start_year": ("start", "start date"),
    "first_posted_year": ("first posted", "first posted date"),
}


@dataclass
class Bucket:
    key: str
    label: str
    trials: dict[str, tuple[Evidence, ...]] = field(default_factory=dict)  # nct_id -> evidence
    estimated: set[str] = field(default_factory=set)

    def add(self, nct_id: str, value: Value) -> None:
        self.trials[nct_id] = value.evidence
        if value.estimated:
            self.estimated.add(nct_id)


@dataclass
class Grouping:
    buckets: dict[str, Bucket]
    excluded: Counter[str]
    placed: set[str]  # trials that appear in at least one bucket


def nct_id(study: dict[str, Any]) -> str:
    return str(value_at(study, "protocolSection.identificationModule.nctId"))


def _missing_value(dimension: str, study: dict[str, Any]) -> Value:
    path = MISSING_PATHS.get(dimension)
    evidence = (Evidence(path, None),) if path and value_at(study, path) in (None, [], "") else ()
    return Value(NOT_REPORTED, NOT_REPORTED_LABEL, evidence)


def year_range(
    studies: Sequence[dict[str, Any]], dim: Dimension, plan: QueryPlan, now_year: int
) -> tuple[int, int]:
    """The plan's years, else from the earliest year in the data to the current year (Q10)."""
    hi = plan.filters.start_year_max or now_year
    lo = plan.filters.start_year_min
    if lo is None:
        years = [int(v.key) for s in studies for v in extract(s, dim.key)]
        lo = min((y for y in years if y <= hi), default=hi)
    return lo, hi


def group(
    studies: Sequence[dict[str, Any]],
    dim: Dimension,
    plan: QueryPlan,
    *,
    years: tuple[int, int] | None = None,
) -> Grouping:
    opts = plan.options
    buckets: dict[str, Bucket] = {}
    excluded: Counter[str] = Counter()
    placed: set[str] = set()
    include_unknown = opts.include_unknown is not False
    lo, hi = years or (0, 9999)

    for study in studies:
        trial = nct_id(study)
        values = extract(
            study,
            dim.key,
            phase_mode=opts.phase_mode or "combined",
            condition_source=opts.condition_source or "mesh",
        )
        if dim.kind is DimensionKind.TIME:
            word, missing = TIME_WORDS[dim.key]
            if not values:
                excluded[f"no {missing}"] += 1
                continue
            year = int(values[0].key)
            if year > hi:
                excluded[f"{word} after {hi}"] += 1
                continue
            if year < lo:
                excluded[f"{word} before {lo}"] += 1
                continue
        elif not values:
            if not include_unknown:
                excluded[f"no {dim.label.lower()} reported"] += 1
                continue
            values = [_missing_value(dim.key, study)]
        for value in values:
            buckets.setdefault(value.key, Bucket(value.key, value.label)).add(trial, value)
        placed.add(trial)

    if dim.kind is DimensionKind.TIME and years:  # zero-fill the whole range
        for year in range(lo, hi + 1):
            buckets.setdefault(str(year), Bucket(str(year), str(year)))
    return Grouping(buckets, excluded, placed)
