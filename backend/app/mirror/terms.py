"""Terms: the parts of a search that ClinicalTrials.gov's search engine interprets (design Q22).

A condition, drug, sponsor or place is matched by the API with its synonyms, MeSH terms or
phrase rules, so the mirror never decides it: the API resolves each term to a set of NCT IDs.
Codes, booleans, date ranges and statuses are plain fields that the mirror evaluates itself.
"""

from dataclasses import dataclass

from app.ctgov.compiler import Clause, Search
from app.ctgov.essie import And, Area, Node, Not, Or, Phrase, to_essie


@dataclass(frozen=True)
class Term:
    param: str  # query.cond | query.intr | query.lead | query.spons | filter.advanced
    expression: str  # Essie text of one filter value

    @property
    def key(self) -> str:
        return f"{self.param}|{self.expression}"

    def search(self) -> Search:
        return Search({self.param: self.expression})


def _has_phrase(node: Node) -> bool:
    match node:
        case Phrase():
            return True
        case Area(_, term):
            return isinstance(term, Phrase)
        case And(items) | Or(items):
            return any(_has_phrase(i) for i in items)
        case Not(item):
            return _has_phrase(item)
    return False


def split(search: Search) -> tuple[list[list[Term]], list[Clause]] | None:
    """The search's terms (an AND of filters, each an OR of terms) and its structured clauses.

    None when the search has no clauses to split (written as parameters only).
    """
    if search.clauses is None:
        return None
    terms: list[list[Term]] = []
    structured: list[Clause] = []
    for clause in search.clauses:
        if not _has_phrase(clause.node):
            structured.append(clause)
            continue
        values = clause.node.items if isinstance(clause.node, Or) else [clause.node]
        terms.append([Term(clause.param, to_essie(v)) for v in values])
    return terms, structured
