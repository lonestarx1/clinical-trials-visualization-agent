"""Raw study JSON -> the values a chart groups by, each with exact evidence (Q9-Q11, Q14).

Normalisation changes how values are grouped, never which trials count. Every
value keeps the raw API excerpts it came from, with the exact JSON path, so a
citation can be checked against the record.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from app.registry import enums as e

Scalar = str | int | float | bool | None

PS = "protocolSection"
DESIGN = f"{PS}.designModule"
STATUS = f"{PS}.statusModule"
SPONSORS = f"{PS}.sponsorCollaboratorsModule"
INTERVENTIONS = f"{PS}.armsInterventionsModule.interventions"
LOCATIONS = f"{PS}.contactsLocationsModule.locations"
ELIGIBILITY = f"{PS}.eligibilityModule"

NO_PHASE = "NO_PHASE"
NO_PHASE_LABEL = "No phase (observational / expanded access)"
DRUG_TYPES = {"DRUG", "BIOLOGICAL"}
INVESTIGATOR_ROLES = {"PRINCIPAL_INVESTIGATOR", "SUB_INVESTIGATOR"}


@dataclass(frozen=True)
class Evidence:
    field: str  # exact JSON path in the API record, e.g. "...phases[1]"
    excerpt: Scalar  # the raw value at that path (None = the field is absent)


@dataclass(frozen=True)
class Value:
    key: str  # group key (normalised)
    label: str  # display label
    evidence: tuple[Evidence, ...]
    estimated: bool = False


@dataclass(frozen=True)
class Number:
    value: float
    evidence: tuple[Evidence, ...]
    estimated: bool = False


Extractor = Callable[[dict[str, Any]], list[Value]]

_STEP = re.compile(r"([^.\[\]]+)(?:\[(\d+)\])?")


def value_at(study: dict[str, Any], path: str) -> Any:
    """Value at a dotted path with optional list indexes, or None if absent."""
    node: Any = study
    for name, index in _STEP.findall(path):
        if not isinstance(node, dict) or name not in node:
            return None
        node = node[name]
        if index:
            if not isinstance(node, list) or int(index) >= len(node):
                return None
            node = node[int(index)]
    return node


def _items(study: dict[str, Any], path: str) -> list[tuple[str, Any]]:
    """(indexed path, item) for each element of the list at `path`."""
    items = value_at(study, path)
    return (
        [(f"{path}[{i}]", item) for i, item in enumerate(items)] if isinstance(items, list) else []
    )


def normalise_name(text: str) -> str:
    return " ".join(text.split()).casefold()


def _distinct(values: list[Value]) -> list[Value]:
    """First occurrence of each key, in record order."""
    seen: set[str] = set()
    kept = []
    for value in values:
        if value.key not in seen:
            seen.add(value.key)
            kept.append(value)
    return kept


# ---------- enums and booleans ----------


def _label(enum: type[e.LabelledEnum] | None, code: str) -> str:
    member = enum._value2member_map_.get(code) if enum else None
    return member.label if isinstance(member, e.LabelledEnum) else code


def _enum_single(path: str, enum: type[e.LabelledEnum]) -> Extractor:
    def extract_one(study: dict[str, Any]) -> list[Value]:
        code = value_at(study, path)
        return [Value(code, _label(enum, code), (Evidence(path, code),))] if code else []

    return extract_one


def _enum_list(
    path: str, enum: type[e.LabelledEnum] | None, item_field: str | None = None
) -> Extractor:
    """Distinct values of a list (enum codes, or plain names when `enum` is None)."""

    def extract_many(study: dict[str, Any]) -> list[Value]:
        found = []
        for item_path, item in _items(study, path):
            field = f"{item_path}.{item_field}" if item_field else item_path
            code = item.get(item_field) if item_field else item
            if code:
                found.append(Value(code, _label(enum, code), (Evidence(field, code),)))
        return _distinct(found)

    return extract_many


def _boolean(path: str) -> Extractor:
    def extract_flag(study: dict[str, Any]) -> list[Value]:
        flag = value_at(study, path)
        if not isinstance(flag, bool):
            return []
        member = e.YesNo.TRUE if flag else e.YesNo.FALSE
        return [Value(member.value, member.label, (Evidence(path, flag),))]

    return extract_flag


def _phase(study: dict[str, Any], phase_mode: str) -> list[Value]:
    phases = value_at(study, f"{DESIGN}.phases")
    if phases is None:  # observational and expanded-access records have no phases key
        study_type = value_at(study, f"{DESIGN}.studyType")
        return [Value(NO_PHASE, NO_PHASE_LABEL, (Evidence(f"{DESIGN}.studyType", study_type),))]
    entries = [(p, Evidence(path, p)) for path, p in _items(study, f"{DESIGN}.phases")]
    if phase_mode == "split":
        return _distinct([Value(p, _label(e.Phase, p), (ev,)) for p, ev in entries])
    if not entries:
        return []
    order = list(e.Phase._value2member_map_)
    entries.sort(key=lambda pe: order.index(pe[0]) if pe[0] in order else len(order))
    key = "/".join(p for p, _ in entries)
    label = "/".join(_label(e.Phase, p) for p, _ in entries)
    return [Value(key, label, tuple(ev for _, ev in entries))]


# ---------- dates ----------


def _year(path: str, type_path: str | None) -> Extractor:
    def extract_year(study: dict[str, Any]) -> list[Value]:
        raw = value_at(study, path)
        if not isinstance(raw, str) or len(raw) < 4:
            return []
        estimated = bool(type_path) and value_at(study, type_path or "") == "ESTIMATED"
        return [Value(raw[:4], raw[:4], (Evidence(path, raw),), estimated)]

    return extract_year


def parse_partial_date(raw: Any) -> date | None:
    """yyyy, yyyy-MM or yyyy-MM-dd -> a date (missing parts become the first day)."""
    if not isinstance(raw, str):
        return None
    parts = [int(p) for p in raw.split("-")]
    while len(parts) < 3:
        parts.append(1)
    try:
        return date(parts[0], parts[1], parts[2])
    except ValueError:
        return None


# ---------- names ----------


def _names(path: str, item_field: str | None = None, *, many: bool = False) -> Extractor:
    """Names at `path`: one string, a list of strings (many), or a list of objects (item_field)."""

    def extract_names(study: dict[str, Any]) -> list[Value]:
        if item_field is None and not many:
            name = value_at(study, path)
            return (
                [Value(normalise_name(name), name.strip(), (Evidence(path, name),))] if name else []
            )
        found = []
        for item_path, item in _items(study, path):
            name = item.get(item_field) if isinstance(item, dict) else item
            field = f"{item_path}.{item_field}" if item_field else item_path
            if isinstance(name, str) and name.strip():
                found.append(Value(normalise_name(name), name.strip(), (Evidence(field, name),)))
        return _distinct(found)

    return extract_names


_PLACEBO = re.compile(r"\b(placebo|vehicle|sham)\b", re.IGNORECASE)
_DOSE = re.compile(r"\b\d+(\.\d+)?\s*(mg|mcg|µg|g|ml|iu|units?)(/(kg|m2|m²|ml|day))?\b", re.I)
_FORM = re.compile(r"\b(injection|tablets?|capsules?|infusion|oral solution|solution)\b", re.I)
_MARKS = re.compile(r"[®™©]|\([^)]*\)|\[[^\]]*\]")


def clean_drug_name(name: str) -> str:
    """Drop dose, dosage form, trademark signs and bracketed text; then case-fold."""
    for pattern in (_MARKS, _DOSE, _FORM):
        name = pattern.sub(" ", name)
    return normalise_name(name)


def _drugs(study: dict[str, Any]) -> list[Value]:
    drug_entries = [
        (path, item)
        for path, item in _items(study, INTERVENTIONS)
        if isinstance(item, dict) and item.get("type") in DRUG_TYPES
    ]
    if not drug_entries:
        return []
    mesh = _names("derivedSection.interventionBrowseModule.meshes", "term")(study)
    if mesh:
        return mesh
    found = []
    for path, item in drug_entries:
        name = item.get("name")
        if not isinstance(name, str) or _PLACEBO.search(name):
            continue
        key = clean_drug_name(name)
        if key:
            found.append(Value(key, " ".join(name.split()), (Evidence(f"{path}.name", name),)))
    return _distinct(found)


def _conditions(study: dict[str, Any], source: str) -> list[Value]:
    if source == "raw":
        return _names(f"{PS}.conditionsModule.conditions", many=True)(study)
    return _names("derivedSection.conditionBrowseModule.meshes", "term")(study)


# ---------- locations ----------


def _us_states(study: dict[str, Any]) -> list[Value]:
    found = []
    for path, loc in _items(study, LOCATIONS):
        state = loc.get("state")
        if loc.get("country") == "United States" and state:
            evidence = (
                Evidence(f"{path}.country", "United States"),
                Evidence(f"{path}.state", state),
            )
            found.append(Value(state, state, evidence))  # API names, kept as-is like countries
    return _distinct(found)


def _sites(study: dict[str, Any]) -> list[Value]:
    found = []
    for path, loc in _items(study, LOCATIONS):
        if not loc.get("facility"):
            continue
        parts = [(f, loc.get(f)) for f in ("facility", "city", "country") if loc.get(f)]
        key = "|".join(normalise_name(v) for _, v in parts)
        label = ", ".join(" ".join(v.split()) for _, v in parts)
        found.append(Value(key, label, tuple(Evidence(f"{path}.{f}", v) for f, v in parts)))
    return _distinct(found)


def _investigators(study: dict[str, Any]) -> list[Value]:
    """Site-level PIs and sub-investigators; credentials after the first comma removed."""
    found = []
    for loc_path, _ in _items(study, LOCATIONS):
        for path, contact in _items(study, f"{loc_path}.contacts"):
            name = contact.get("name")
            if contact.get("role") in INVESTIGATOR_ROLES and isinstance(name, str):
                clean = " ".join(name.split(",")[0].split())
                if clean:
                    found.append(Value(clean.casefold(), clean, (Evidence(f"{path}.name", name),)))
    return _distinct(found)


# ---------- dispatch ----------

_EXTRACTORS: dict[str, Extractor] = {
    "status": _enum_single(f"{STATUS}.overallStatus", e.Status),
    "study_type": _enum_single(f"{DESIGN}.studyType", e.StudyType),
    "sponsor_class": _enum_single(f"{SPONSORS}.leadSponsor.class", e.AgencyClass),
    "intervention_type": _enum_list(INTERVENTIONS, e.InterventionType, "type"),
    "age_group": _enum_list(f"{ELIGIBILITY}.stdAges", e.StandardAge),
    "sex": _enum_single(f"{ELIGIBILITY}.sex", e.Sex),
    "healthy_volunteers": _boolean(f"{ELIGIBILITY}.healthyVolunteers"),
    "allocation": _enum_single(f"{DESIGN}.designInfo.allocation", e.Allocation),
    "masking": _enum_single(f"{DESIGN}.designInfo.maskingInfo.masking", e.Masking),
    "primary_purpose": _enum_single(f"{DESIGN}.designInfo.primaryPurpose", e.PrimaryPurpose),
    "has_results": _boolean("hasResults"),
    "start_year": _year(f"{STATUS}.startDateStruct.date", f"{STATUS}.startDateStruct.type"),
    "first_posted_year": _year(f"{STATUS}.studyFirstPostDateStruct.date", None),
    "country": _enum_list(LOCATIONS, None, "country"),
    "us_state": _us_states,
    "sponsor": _names(f"{SPONSORS}.leadSponsor.name"),
    "collaborator": _names(f"{SPONSORS}.collaborators", "name"),
    "drug": _drugs,
    "site": _sites,
    "investigator": _investigators,
}


def extract(
    study: dict[str, Any],
    dimension: str,
    *,
    phase_mode: Literal["combined", "split"] = "combined",
    condition_source: Literal["mesh", "raw"] = "mesh",
) -> list[Value]:
    """The trial's values for a dimension. An empty list means "not reported"."""
    if dimension == "phase":
        return _phase(study, phase_mode)
    if dimension == "condition":
        return _conditions(study, condition_source)
    return _EXTRACTORS[dimension](study)


def extract_number(study: dict[str, Any], key: str) -> Number | None:
    """A per-trial number (numeric dimensions and enrollment measures), or None if missing."""
    if key == "enrollment":
        path = f"{DESIGN}.enrollmentInfo"
        count = value_at(study, f"{path}.count")
        if not isinstance(count, int):
            return None
        estimated = value_at(study, f"{path}.type") == "ESTIMATED"
        return Number(count, (Evidence(f"{path}.count", count),), estimated)
    if key == "duration_months":
        start_raw = value_at(study, f"{STATUS}.startDateStruct.date")
        end_raw = value_at(study, f"{STATUS}.completionDateStruct.date")
        start, end = parse_partial_date(start_raw), parse_partial_date(end_raw)
        if start is None or end is None:
            return None
        estimated = "ESTIMATED" in (
            value_at(study, f"{STATUS}.startDateStruct.type"),
            value_at(study, f"{STATUS}.completionDateStruct.type"),
        )
        evidence: tuple[Evidence, ...] = (
            Evidence(f"{STATUS}.startDateStruct.date", start_raw),
            Evidence(f"{STATUS}.completionDateStruct.date", end_raw),
        )
        return Number(round((end - start).days / 30.4375, 1), evidence, estimated)
    if key == "site_count":
        locations = _items(study, LOCATIONS)
        evidence = tuple(
            Evidence(f"{path}.facility", loc.get("facility")) for path, loc in locations[:3]
        )
        return Number(len(locations), evidence)
    raise KeyError(f"{key} is not a numeric dimension")
