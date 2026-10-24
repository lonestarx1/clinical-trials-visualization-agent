"""Plan filters -> ClinicalTrials.gov search parameters (design Q7).

OR within a filter, AND across filters (D7.2). Each comparison group becomes
its own search: shared filters AND the group's filters.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlencode

from app.ctgov.countries import resolve_country
from app.ctgov.essie import And, Area, Code, Node, Or, Phrase, Range, to_essie
from app.schemas.plan import Filters, QueryPlan


class CompileError(ValueError):
    pass


@dataclass(frozen=True)
class Clause:
    """One filter of a search: its parameter and expression, ANDed with the other filters."""

    param: str
    node: Node


@dataclass(frozen=True)
class Search:
    """One API search: the /studies query parameters, without paging or fields.

    `clauses` are the filters the parameters were built from, so the mirror can evaluate the
    same search (design Q22); None for a search written as parameters only.
    """

    params: dict[str, str]
    group: str | None = None
    warnings: list[str] = field(default_factory=list)
    clauses: tuple[Clause, ...] | None = None

    def url(self, base_url: str) -> str:
        return f"{base_url}/studies?{urlencode(sorted(self.params.items()))}"

    def narrow(self, clause: Node) -> "Search":
        """The same search AND one more filter.advanced clause."""
        existing = self.params.get("filter.advanced")
        extra = to_essie(clause)
        advanced = f"({existing} AND {extra})" if existing else extra
        clauses = (
            None if self.clauses is None else (*self.clauses, Clause("filter.advanced", clause))
        )
        return Search(
            self.params | {"filter.advanced": advanced}, self.group, self.warnings, clauses
        )


@dataclass
class _Parts:
    """Compiled pieces of one Filters object, before they're joined into parameters."""

    nodes: dict[str, list[Node]] = field(default_factory=lambda: defaultdict(list))
    statuses: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _any_of(field_name: str, codes: Sequence[StrEnum]) -> Node:
    return Or([Area(field_name, Code(c.value)) for c in codes])


def _broad_condition(term: str) -> Node:
    """Words may match separately (like the API's unquoted search), each still quoted."""
    return And([Phrase(word) for word in term.split()])


def _parts(f: Filters) -> _Parts:
    parts = _Parts()
    advanced = parts.nodes["filter.advanced"]

    if f.drugs:
        if f.match_mode == "strict":
            advanced.append(Or([Area("InterventionNameSearch", Phrase(d)) for d in f.drugs]))
        else:
            parts.nodes["query.intr"].append(Or([Phrase(d) for d in f.drugs]))
    if f.conditions:
        terms: list[Node] = (
            [Phrase(c) for c in f.conditions]
            if f.match_mode == "strict"
            else [_broad_condition(c) for c in f.conditions]
        )
        parts.nodes["query.cond"].append(Or(terms))
    if f.sponsors:
        param = "query.lead" if f.sponsor_role == "lead" else "query.spons"
        parts.nodes[param].append(Or([Phrase(s) for s in f.sponsors]))
    if f.countries:
        names = []
        for given in f.countries:
            name, known = resolve_country(given)
            if not known:
                parts.warnings.append(f"Country '{given}' is not a known ClinicalTrials.gov name.")
            names.append(name)
        advanced.append(Or([Area("LocationCountry", Phrase(n)) for n in names]))
    if f.us_states:
        advanced.append(Or([Area("LocationState", Phrase(s)) for s in f.us_states]))

    for piece, codes in (
        ("Phase", f.phases),
        ("StudyType", f.study_types),
        ("LeadSponsorClass", f.sponsor_classes),
        ("StdAge", f.age_groups),
        ("Sex", f.sexes),
        ("DesignAllocation", f.allocations),
        ("DesignMasking", f.maskings),
        ("DesignPrimaryPurpose", f.primary_purposes),
    ):
        if codes:
            advanced.append(_any_of(piece, codes))
    for piece, flag in (("HealthyVolunteers", f.healthy_volunteers), ("HasResults", f.has_results)):
        if flag is not None:
            advanced.append(Area(piece, Code("true" if flag else "false")))

    if f.start_year_min is not None or f.start_year_max is not None:
        lo = f"{f.start_year_min}-01-01" if f.start_year_min is not None else "MIN"
        hi = f"{f.start_year_max}-12-31" if f.start_year_max is not None else "MAX"
        advanced.append(Area("StartDate", Range(lo, hi)))

    parts.statuses = [s.value for s in f.statuses]
    return parts


def _to_search(all_parts: Sequence[_Parts], group: str | None = None) -> Search:
    params: dict[str, str] = {}
    clauses: list[Clause] = []
    for param in ("query.cond", "query.intr", "query.lead", "query.spons", "filter.advanced"):
        nodes = [n for p in all_parts for n in p.nodes.get(param, [])]
        if nodes:
            params[param] = to_essie(And(nodes))
            clauses += [Clause(param, n) for n in nodes]

    status_lists = [p.statuses for p in all_parts if p.statuses]
    if status_lists:
        common = [s for s in status_lists[0] if all(s in other for other in status_lists[1:])]
        if not common:
            raise CompileError(f"group {group!r}: shared and group statuses have nothing in common")
        params["filter.overallStatus"] = "|".join(common)
        clauses.append(Clause("filter.overallStatus", Or([Code(s) for s in common])))

    return Search(params, group, [w for p in all_parts for w in p.warnings], tuple(clauses))


def compile_filters(filters: Filters) -> Search:
    return _to_search([_parts(filters)])


def compile_plan(plan: QueryPlan) -> list[Search]:
    """One search per comparison group, or a single search without groups."""
    shared = _parts(plan.filters)
    if not plan.groups:
        return [_to_search([shared])]
    return [_to_search([shared, _parts(g.filters)], g.label) for g in plan.groups]
