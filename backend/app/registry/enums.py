"""API enums with display labels (values and order as in /studies/enums)."""

from enum import StrEnum
from typing import Self


class LabelledEnum(StrEnum):
    label: str

    def __new__(cls, value: str, label: str) -> Self:
        member = str.__new__(cls, value)
        member._value_ = value
        member.label = label
        return member


class Phase(LabelledEnum):
    NA = "NA", "Not Applicable"
    EARLY_PHASE1 = "EARLY_PHASE1", "Early Phase 1"
    PHASE1 = "PHASE1", "Phase 1"
    PHASE2 = "PHASE2", "Phase 2"
    PHASE3 = "PHASE3", "Phase 3"
    PHASE4 = "PHASE4", "Phase 4"


class Status(LabelledEnum):
    ACTIVE_NOT_RECRUITING = "ACTIVE_NOT_RECRUITING", "Active, not recruiting"
    COMPLETED = "COMPLETED", "Completed"
    ENROLLING_BY_INVITATION = "ENROLLING_BY_INVITATION", "Enrolling by invitation"
    NOT_YET_RECRUITING = "NOT_YET_RECRUITING", "Not yet recruiting"
    RECRUITING = "RECRUITING", "Recruiting"
    SUSPENDED = "SUSPENDED", "Suspended"
    TERMINATED = "TERMINATED", "Terminated"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"
    AVAILABLE = "AVAILABLE", "Available"
    NO_LONGER_AVAILABLE = "NO_LONGER_AVAILABLE", "No longer available"
    TEMPORARILY_NOT_AVAILABLE = "TEMPORARILY_NOT_AVAILABLE", "Temporarily not available"
    APPROVED_FOR_MARKETING = "APPROVED_FOR_MARKETING", "Approved for marketing"
    WITHHELD = "WITHHELD", "Withheld"
    UNKNOWN = "UNKNOWN", "Unknown status"


class StudyType(LabelledEnum):
    EXPANDED_ACCESS = "EXPANDED_ACCESS", "Expanded access"
    INTERVENTIONAL = "INTERVENTIONAL", "Interventional"
    OBSERVATIONAL = "OBSERVATIONAL", "Observational"


class AgencyClass(LabelledEnum):
    NIH = "NIH", "NIH"
    FED = "FED", "Other U.S. federal agency"
    OTHER_GOV = "OTHER_GOV", "Other government"
    INDIV = "INDIV", "Individual"
    INDUSTRY = "INDUSTRY", "Industry"
    NETWORK = "NETWORK", "Network"
    AMBIG = "AMBIG", "Ambiguous"
    OTHER = "OTHER", "Other (incl. academic)"
    UNKNOWN = "UNKNOWN", "Unknown"


class InterventionType(LabelledEnum):
    BEHAVIORAL = "BEHAVIORAL", "Behavioral"
    BIOLOGICAL = "BIOLOGICAL", "Biological"
    COMBINATION_PRODUCT = "COMBINATION_PRODUCT", "Combination product"
    DEVICE = "DEVICE", "Device"
    DIAGNOSTIC_TEST = "DIAGNOSTIC_TEST", "Diagnostic test"
    DIETARY_SUPPLEMENT = "DIETARY_SUPPLEMENT", "Dietary supplement"
    DRUG = "DRUG", "Drug"
    GENETIC = "GENETIC", "Genetic"
    PROCEDURE = "PROCEDURE", "Procedure"
    RADIATION = "RADIATION", "Radiation"
    OTHER = "OTHER", "Other"


class StandardAge(LabelledEnum):
    CHILD = "CHILD", "Child"
    ADULT = "ADULT", "Adult"
    OLDER_ADULT = "OLDER_ADULT", "Older adult"


class Sex(LabelledEnum):
    FEMALE = "FEMALE", "Female"
    MALE = "MALE", "Male"
    ALL = "ALL", "All"


class Allocation(LabelledEnum):
    RANDOMIZED = "RANDOMIZED", "Randomized"
    NON_RANDOMIZED = "NON_RANDOMIZED", "Non-randomized"
    NA = "NA", "Not applicable"


class Masking(LabelledEnum):
    NONE = "NONE", "None (open label)"
    SINGLE = "SINGLE", "Single"
    DOUBLE = "DOUBLE", "Double"
    TRIPLE = "TRIPLE", "Triple"
    QUADRUPLE = "QUADRUPLE", "Quadruple"


class PrimaryPurpose(LabelledEnum):
    TREATMENT = "TREATMENT", "Treatment"
    PREVENTION = "PREVENTION", "Prevention"
    DIAGNOSTIC = "DIAGNOSTIC", "Diagnostic"
    ECT = "ECT", "Educational/counseling/training"
    SUPPORTIVE_CARE = "SUPPORTIVE_CARE", "Supportive care"
    SCREENING = "SCREENING", "Screening"
    HEALTH_SERVICES_RESEARCH = "HEALTH_SERVICES_RESEARCH", "Health services research"
    BASIC_SCIENCE = "BASIC_SCIENCE", "Basic science"
    DEVICE_FEASIBILITY = "DEVICE_FEASIBILITY", "Device feasibility"
    OTHER = "OTHER", "Other"


class YesNo(LabelledEnum):
    """Boolean fields, written as the API's search tokens."""

    TRUE = "true", "Yes"
    FALSE = "false", "No"
