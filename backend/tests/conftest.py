"""Shared test configuration.

The test session runs against a dedicated database named "<development database>_test",
which is dropped and recreated at the start of every session. It never touches the
development database. Each test runs inside a transaction that is rolled back at the end.
"""

import os
from pathlib import Path

# --- Point the whole process at the test database BEFORE any application import. ---
# alembic/env.py and the application settings both read DATABASE_URL from the environment,
# so overriding it here is what actually redirects migrations and tests.
from sqlalchemy.engine import make_url

_dev_url = make_url(os.environ["DATABASE_URL"])
_dev_db_name = _dev_url.database or "adops360"
TEST_DB_NAME = _dev_db_name if _dev_db_name.endswith("_test") else f"{_dev_db_name}_test"
_test_url = _dev_url.set(database=TEST_DB_NAME)
TEST_DATABASE_URL = _test_url.render_as_string(hide_password=False)

# Safeguard: the tests must never run against a database that is not a "_test" one.
assert TEST_DB_NAME.endswith("_test"), "Refusing to run tests outside a *_test database"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _recreate_test_database() -> None:
    """Drop and create the test database from the maintenance database."""
    admin_engine = create_engine(_test_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create a clean test database and migrate it to head."""
    _recreate_test_database()
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(alembic_config, "head")  # env.py reads DATABASE_URL (the test one)
    yield


@pytest.fixture(scope="session")
def test_engine(setup_test_db):
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def test_db_session_factory(test_engine):
    """Kept for compatibility. Sessions from this factory are NOT rolled back per test."""
    return sessionmaker(bind=test_engine, expire_on_commit=False)


@pytest.fixture
def rolled_back_session(test_engine):
    """A session whose changes are rolled back when the test ends.

    The session joins an outer transaction through savepoints, so commit() and rollback()
    inside a test behave normally without leaving data behind.
    """
    connection = test_engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def test_db_session(rolled_back_session):
    """The default per-test session. Infrastructure tests shadow it; see tests/infrastructure/conftest.py."""
    return rolled_back_session
