"""Terms: the parts of a search that ClinicalTrials.gov's search engine interprets (design Q22).

A condition, drug, sponsor or place is matched by the API with its synonyms, MeSH terms or
phrase rules, so the mirror never decides it: the API resolves each term to a set of NCT IDs.
Codes, booleans, date ranges and statuses are plain fields that the mirror evaluates itself.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ctgov.client import CtgovClient
from app.ctgov.compiler import Clause, Search
from app.ctgov.essie import And, Area, Node, Not, Or, Phrase, Range, to_essie
from app.mirror.sync import OVERLAP
from app.store import mirror
from app.store import terms as store

RESOLVE_AGAIN_AFTER = timedelta(days=7)  # the API's synonym and MeSH tables change too


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


async def _ids(ctgov: CtgovClient, search: Search) -> set[str]:
    ids: set[str] = set()
    async for studies, _ in ctgov.pages(search, ["NCTId"]):
        ids.update(str(s["protocolSection"]["identificationModule"]["nctId"]) for s in studies)
    return ids


async def term_set(
    ctgov: CtgovClient,
    sessions: async_sessionmaker[AsyncSession],
    term: Term,
    *,
    data_timestamp: str,
    now: datetime | None = None,
) -> set[str]:
    """The trials `term` matches at `data_timestamp`: stored, refreshed, or listed by the API.

    A refresh asks only which recently changed trials match now, and drops every changed trial
    the mirror knows of, so the mirror must be current at `data_timestamp`.
    """
    now = now or datetime.now(UTC)
    current = datetime.fromisoformat(data_timestamp).replace(tzinfo=UTC)
    async with sessions() as s:
        row = await store.get_set(s, term.key)
        old = await store.members(s, term.key) if row is not None else set()
        if row is not None and row.data_timestamp == current:
            return old
        if row is not None and now - row.resolved_at <= RESOLVE_AGAIN_AFTER:
            since = (row.checked_at - OVERLAP).date()
            recent = Area("LastUpdatePostDate", Range(since.isoformat(), "MAX"))
            matched = await _ids(ctgov, term.search().narrow(recent))
            ids = (old - await mirror.changed_since(s, since)) | matched
            resolved_at = row.resolved_at
        else:
            ids, resolved_at = await _ids(ctgov, term.search()), now
        await store.save(
            s,
            term_key=term.key,
            param=term.param,
            expression=term.expression,
            ids=ids,
            old=old,
            data_timestamp=data_timestamp,
            checked_at=now,
            resolved_at=resolved_at,
        )
        await s.commit()
    return ids
