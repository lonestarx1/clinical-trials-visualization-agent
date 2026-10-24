import os

import pytest

from app.store.db import check_database, create_engine

pytestmark = pytest.mark.db


async def test_real_database_reports_true() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    assert await check_database(engine) is True
    await engine.dispose()
