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
