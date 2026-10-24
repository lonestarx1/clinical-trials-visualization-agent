"""Database engine and connectivity check (Postgres via SQLAlchemy async)."""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

log = logging.getLogger(__name__)


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


async def check_database(engine: AsyncEngine, timeout_seconds: float = 3) -> bool:
    """True if the database answers a trivial query in time. Never raises."""
    try:
        async with asyncio.timeout(timeout_seconds), engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # any failure means "not healthy"
        log.warning("database check failed: %s", type(exc).__name__)
        return False
    return True
