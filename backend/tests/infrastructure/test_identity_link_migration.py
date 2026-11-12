"""The migration that adds the identity link columns to users, run on a throwaway database holding a user."""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url

from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL

BEFORE = "439b6b8481f8"  # add the margin tables
AFTER = "e33b0a845ea3"  # the migration under test: the identity link columns
SCRATCH_DB = "adops360_identity_link_migration_test"
LINK_COLUMNS = {"identity_issuer", "identity_subject"}


@pytest.fixture
def scratch(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Config, Engine]]:
    """An empty database migrated to the revision before the identity columns, with one user; dropped afterwards."""
    base = make_url(TEST_DATABASE_URL)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    url = base.set(database=SCRATCH_DB)
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, BEFORE)
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (email, full_name, is_active) VALUES ('previo@example.com', 'Previo', true)"))
    try:
        yield config, engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def _user_columns(engine: Engine) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns("users")}


def test_upgrading_adds_the_columns_and_leaves_an_existing_user_without_a_link(
    scratch: tuple[Config, Engine],
) -> None:
    config, engine = scratch
    assert not LINK_COLUMNS & _user_columns(engine)

    command.upgrade(config, AFTER)

    assert LINK_COLUMNS <= _user_columns(engine)
    with engine.connect() as connection:
        row = connection.execute(text("SELECT email, identity_issuer, identity_subject FROM users")).one()
    assert tuple(row) == ("previo@example.com", None, None)


def test_downgrading_removes_the_columns_and_keeps_the_user(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)

    command.downgrade(config, BEFORE)

    assert not LINK_COLUMNS & _user_columns(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM users")).scalar() == 1


def test_upgrading_again_after_a_downgrade_is_clean(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch

    command.upgrade(config, AFTER)
    command.downgrade(config, BEFORE)
    command.upgrade(config, AFTER)

    assert LINK_COLUMNS <= _user_columns(engine)
