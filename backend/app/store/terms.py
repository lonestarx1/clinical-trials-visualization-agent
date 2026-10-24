"""Term sets (design Q22): the NCT IDs each search term matches, as the API resolved them."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.models import TermMember, TermSet

INSERT_BATCH = 5000


async def get_set(session: AsyncSession, term_key: str) -> TermSet | None:
    return await session.get(TermSet, term_key)


async def members(session: AsyncSession, term_key: str) -> set[str]:
    return set(
        await session.scalars(select(TermMember.nct_id).where(TermMember.term_key == term_key))
    )


async def save(
    session: AsyncSession,
    *,
    term_key: str,
    param: str,
    expression: str,
    ids: set[str],
    old: set[str],
    data_timestamp: str,
    checked_at: datetime,
    resolved_at: datetime,
) -> None:
    """Store the set's new members (only the difference from `old` is written)."""
    await session.execute(
        pg_insert(TermSet)
        .values(
            term_key=term_key,
            param=param,
            expression=expression,
            size=len(ids),
            data_timestamp=datetime.fromisoformat(data_timestamp).replace(tzinfo=UTC),
            resolved_at=resolved_at,
            checked_at=checked_at,
        )
        .on_conflict_do_update(
            index_elements=["term_key"],
            set_={
                "size": len(ids),
                "data_timestamp": datetime.fromisoformat(data_timestamp).replace(tzinfo=UTC),
                "resolved_at": resolved_at,
                "checked_at": checked_at,
            },
        )
    )
    gone = old - ids
    if gone:
        await session.execute(
            delete(TermMember).where(
                TermMember.term_key == term_key, TermMember.nct_id.in_(list(gone))
            )
        )
    new = sorted(ids - old)
    for i in range(0, len(new), INSERT_BATCH):
        rows = [{"term_key": term_key, "nct_id": n} for n in new[i : i + INSERT_BATCH]]
        await session.execute(pg_insert(TermMember).values(rows).on_conflict_do_nothing())
