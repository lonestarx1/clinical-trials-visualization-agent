"""Dimensions: what a chart can group trials by (design Q1, Q9, Q15).

One entry per dimension. Everything else (planner options, validation, field
selection, aggregation, citations) reads from here.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.registry import enums as e


class DimensionKind(StrEnum):
    CATEGORICAL = "categorical"  # bounded enum values
    ENTITY = "entity"  # open-ended names (drugs, sponsors, countries, ...)
    TIME = "time"  # years
    NUMERIC = "numeric"  # per-trial numbers for histograms and scatter plots


@dataclass(frozen=True)
class Dimension:
    key: str
    label: str
    kind: DimensionKind
    fields: tuple[str, ...]  # API pieces to request when fetching studies
    counting_rule: str
    filter_piece: str | None = None  # piece used in AREA[...] filters and per-bucket counts
    enum: type[e.LabelledEnum] | None = None
    multi_valued: bool = False  # a trial can fall into several buckets


_ONCE = "Each trial is counted once."


def _per_value(thing: str) -> str:
    return f"Each trial is counted once per distinct {thing} it lists."


C, N, T, X = (
    DimensionKind.CATEGORICAL,
    DimensionKind.ENTITY,
    DimensionKind.TIME,
    DimensionKind.NUMERIC,
)

DIMENSIONS: dict[str, Dimension] = {
    d.key: d
    for d in [
        # Categorical (bounded enum values)
        Dimension(
            "phase",
            "Phase",
            C,
            ("Phase", "StudyType"),
            "Each trial is counted once; trials with two phases get a combined bucket "
            "(e.g. Phase 2/Phase 3).",
            "Phase",
            e.Phase,
        ),
        Dimension(
            "status", "Overall status", C, ("OverallStatus",), _ONCE, "OverallStatus", e.Status
        ),
        Dimension("study_type", "Study type", C, ("StudyType",), _ONCE, "StudyType", e.StudyType),
        Dimension(
            "sponsor_class",
            "Lead sponsor type",
            C,
            ("LeadSponsorClass",),
            _ONCE,
            "LeadSponsorClass",
            e.AgencyClass,
        ),
        Dimension(
            "intervention_type",
            "Intervention type",
            C,
            ("InterventionType",),
            _per_value("intervention type"),
            "InterventionType",
            e.InterventionType,
            multi_valued=True,
        ),
        Dimension(
            "age_group",
            "Age group",
            C,
            ("StdAge",),
            _per_value("age group"),
            "StdAge",
            e.StandardAge,
            multi_valued=True,
        ),
        Dimension("sex", "Sex eligibility", C, ("Sex",), _ONCE, "Sex", e.Sex),
        Dimension(
            "healthy_volunteers",
            "Accepts healthy volunteers",
            C,
            ("HealthyVolunteers",),
            _ONCE,
            "HealthyVolunteers",
            e.YesNo,
        ),
        Dimension(
            "allocation",
            "Allocation",
            C,
            ("DesignAllocation",),
            _ONCE,
            "DesignAllocation",
            e.Allocation,
        ),
        Dimension("masking", "Masking", C, ("DesignMasking",), _ONCE, "DesignMasking", e.Masking),
        Dimension(
            "primary_purpose",
            "Primary purpose",
            C,
            ("DesignPrimaryPurpose",),
            _ONCE,
            "DesignPrimaryPurpose",
            e.PrimaryPurpose,
        ),
        Dimension(
            "has_results", "Results posted", C, ("HasResults",), _ONCE, "HasResults", e.YesNo
        ),
        # Time
        Dimension(
            "start_year",
            "Start year",
            T,
            ("StartDate", "StartDateType"),
            "Each trial is counted once, in the year it started (or is expected to start).",
            "StartDate",
        ),
        Dimension(
            "first_posted_year",
            "First posted year",
            T,
            ("StudyFirstPostDate",),
            "Each trial is counted once, in the year it was first posted.",
            "StudyFirstPostDate",
        ),
        # Entities (open-ended names)
        Dimension(
            "country",
            "Country",
            N,
            ("LocationCountry",),
            "Each trial is counted once per country where it has at least one site.",
            "LocationCountry",
            multi_valued=True,
        ),
        Dimension(
            "us_state",
            "U.S. state",
            N,
            ("LocationCountry", "LocationState"),
            "Each trial is counted once per U.S. state where it has at least one site.",
            "LocationState",
            multi_valued=True,
        ),
        Dimension(
            "sponsor",
            "Lead sponsor",
            N,
            ("LeadSponsorName", "LeadSponsorClass"),
            _ONCE,
            "LeadSponsorName",
        ),
        Dimension(
            "collaborator",
            "Collaborator",
            N,
            ("CollaboratorName", "CollaboratorClass"),
            _per_value("collaborator"),
            "CollaboratorName",
            multi_valued=True,
        ),
        Dimension(
            "drug",
            "Drug",
            N,
            ("InterventionName", "InterventionType", "InterventionMeshTerm"),
            _per_value("drug (placebo excluded)"),
            "InterventionName",
            multi_valued=True,
        ),
        Dimension(
            "condition",
            "Condition",
            N,
            ("Condition", "ConditionMeshTerm"),
            _per_value("condition"),
            "Condition",
            multi_valued=True,
        ),
        Dimension(
            "site",
            "Site",
            N,
            ("LocationFacility", "LocationCity", "LocationCountry"),
            _per_value("site"),
            "LocationFacility",
            multi_valued=True,
        ),
        Dimension(
            "investigator",
            "Site investigator",
            N,
            ("LocationFacility", "LocationContactName", "LocationContactRole"),
            _per_value("site investigator"),
            multi_valued=True,
        ),
        # Numeric (per trial)
        Dimension(
            "enrollment",
            "Enrollment",
            X,
            ("EnrollmentCount", "EnrollmentType"),
            "One value per trial: its enrollment (actual or estimated).",
            "EnrollmentCount",
        ),
        Dimension(
            "duration_months",
            "Duration (months)",
            X,
            ("StartDate", "CompletionDate"),
            "One value per trial: months from start to completion (approximate for partial dates).",
        ),
        Dimension(
            "site_count",
            "Number of sites",
            X,
            ("LocationFacility",),
            "One value per trial: its number of listed sites.",
        ),
    ]
}

# Requested for every fetch: needed to cite each trial.
BASE_FIELDS: tuple[str, ...] = ("NCTId", "BriefTitle")
