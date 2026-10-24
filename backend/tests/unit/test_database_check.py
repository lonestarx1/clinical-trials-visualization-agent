from app.store.db import check_database, create_engine


async def test_unreachable_database_reports_false() -> None:
    engine = create_engine("postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none")
    assert await check_database(engine, timeout_seconds=2) is False
    await engine.dispose()
