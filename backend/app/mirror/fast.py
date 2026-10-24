"""Fast mode (design Q22): the API picks the trials, the mirror supplies their records.

For each search: the term sets come from the API (listed once, refreshed after each update),
the structured filters run as SQL over the mirror, and the mirror's number of trials must
equal the live count `prepare()` already made. Only then are the mirror's records used, by the
same aggregation code as live mode. Any check that fails raises FastUnavailable, and the
question is answered live: as slow as live mode, never different.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ctgov.client import CtgovClient, FetchResult
from app.ctgov.retrieval import fields_for
from app.mirror import query
from app.mirror.slices import mirror_fields
from app.mirror.terms import split, term_set
from app.pipeline.run import Prepared
from app.store import mirror
from app.store import terms as term_store

log = logging.getLogger(__name__)

Sessions = async_sessionmaker[AsyncSession]
Status = Literal["ready", "syncing", "not_loaded"]


class FastUnavailable(Exception):
    """Fast mode can't answer this question exactly; the message says why, for the user."""


def _ts(data_timestamp: str) -> datetime:
    return datetime.fromisoformat(data_timestamp).replace(tzinfo=UTC)


async def mirror_status(sessions: Sessions, data_timestamp: str) -> tuple[Status, str | None]:
    """Whether the mirror holds the API's current data, and the data timestamp it holds."""
    async with sessions() as s:
        run = await mirror.last_success(s)
    if run is None:
        return "not_loaded", None
    held = run.data_timestamp.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds")
    return ("ready" if run.data_timestamp == _ts(data_timestamp) else "syncing"), held


async def fetch_from_mirror(
    prepared: Prepared,
    ctgov: CtgovClient,
    sessions: Sessions,
    *,
    new_term_max_trials: int,
    max_trials: int,
) -> list[FetchResult]:
    """Each search's matching trials, read from the mirror once every check has passed."""
    if prepared.counted_total:  # checked first: the count is already made, the copy can't beat it
        raise FastUnavailable("ClinicalTrials.gov's own count answers a plain total quicker")
    data_timestamp = prepared.version.data_timestamp
    status, _ = await mirror_status(sessions, data_timestamp)
    if status == "not_loaded":
        raise FastUnavailable("our copy of ClinicalTrials.gov isn't loaded yet")
    if status == "syncing":
        raise FastUnavailable("our copy is still syncing ClinicalTrials.gov's latest update")
    if not set(fields_for(prepared.plan)) <= set(mirror_fields()):
        raise FastUnavailable("this chart needs a field our copy doesn't keep")
    if sum(prepared.counts) > max_trials:
        raise FastUnavailable(f"more than {max_trials:,} trials is too large for fast mode")

    results = []
    for search, live_count in zip(prepared.searches, prepared.counts, strict=True):
        parts = split(search)
        if parts is None:
            raise FastUnavailable("this search can't be evaluated on our copy")
        for term in (t for values in parts[0] for t in values):
            async with sessions() as s:
                known = await term_store.get_set(s, term.key) is not None
            if not known and (n := await ctgov.count(term.search())) > new_term_max_trials:
                raise FastUnavailable(
                    f"the search term {term.expression} ({n:,} trials) is not prepared yet"
                )
            await term_set(ctgov, sessions, term, data_timestamp=data_timestamp)
        async with sessions() as s:
            try:
                count = await query.count(s, search)
                if count != live_count:
                    log.warning(
                        "fast-mode drift: mirror %d, live %d for %s",
                        count,
                        live_count,
                        search.params,
                    )
                    raise FastUnavailable(
                        f"our copy's count ({count:,}) disagreed with ClinicalTrials.gov's "
                        f"({live_count:,})"
                    )
                studies = await query.records(s, search)
            except query.NotInMirror as exc:
                raise FastUnavailable("this search can't be evaluated on our copy") from exc
        results.append(FetchResult(studies, count))
    return results


CITATION_FIELDS = {"citations", "citations_truncated"}  # samples may differ; counts may not


def _points(visualization: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Each data point's values (the measure, counts, labels), without its citation sample."""
    data = visualization["data"]
    points = [*data["nodes"], *data["edges"]] if isinstance(data, dict) else data
    return {
        str(p["key"]): {k: v for k, v in sorted(p.items()) if k not in CITATION_FIELDS}
        for p in points
    }


def differences(fast: dict[str, Any], live: dict[str, Any]) -> list[str]:
    """Every data point whose value or number of trials differs (shadow runs, design Q22)."""
    a, b = _points(fast), _points(live)
    return [
        f"{key}: fast {a.get(key)}, live {b.get(key)}"
        for key in sorted(a.keys() | b.keys())
        if a.get(key) != b.get(key)
    ]
