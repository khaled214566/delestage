"""Shared fixtures.

Pure tests need nothing. Tests marked ``db`` need PostgreSQL with the schema at
head (``alembic upgrade head``); they are SKIPPED, not failed, when the database
is unreachable. Every DB test runs inside a transaction that is rolled back, so
they never modify your dev data.
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


@pytest.fixture(scope="session")
def engine():
    from app.core.config import settings

    eng = create_engine(settings.database_url_sync)
    try:
        with eng.connect() as conn:
            if conn.execute(text("SELECT to_regclass('public.v_sheddable_feeders')")).scalar() is None:
                pytest.skip("schema not at head: run `alembic upgrade head`")
    except OperationalError:
        pytest.skip("database not reachable")
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    """A Session inside a transaction that is always rolled back."""
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()


@pytest.fixture(scope="session")
def _async_db_reachable(engine):
    """Piggybacks on `engine`'s reachability/schema check (session-scoped,
    sync, so it's cheap to share) — the async engine itself must NOT be
    session-scoped: pytest-asyncio gives each test its own event loop by
    default, and an asyncpg connection pool opened on one loop breaks with
    'another operation is in progress' style errors if reused from another."""
    return True


@pytest.fixture()
async def adb(_async_db_reachable):
    """An AsyncSession inside a transaction that is always rolled back —
    the async counterpart of `db`, for calling app.services.* functions.
    Function-scoped end to end (engine included) so it always matches the
    current test's event loop."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.core.config import settings

    aeng = create_async_engine(settings.database_url)
    conn = await aeng.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await aeng.dispose()