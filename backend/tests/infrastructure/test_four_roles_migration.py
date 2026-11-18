"""The migration that inserts the four roles, run on a throwaway database, so a fresh database does not depend on
the development seed."""

from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from scripts.seed_dev_data import seed
from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL

BEFORE = "35164f01d7a1"  # add the trading role
AFTER = "e5d42817a180"  # the migration under test
SCRATCH_DB = "adops360_four_roles_migration_test"
FOUR_ROLES = {"operations", "business", "finance", "trading"}


@pytest.fixture
def scratch(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Config, Engine]]:
    """An empty database, with no migration applied; dropped afterwards."""
    base = make_url(TEST_DATABASE_URL)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    url = base.set(database=SCRATCH_DB)
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    engine = create_engine(url)
    try:
        yield config, engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def _role_rows(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return list(connection.execute(text("SELECT name FROM roles ORDER BY name")).scalars())


def test_on_an_empty_database_the_four_roles_exist_after_the_migration(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch

    command.upgrade(config, AFTER)

    assert _role_rows(engine) == sorted(FOUR_ROLES)


def test_with_trading_already_present_the_other_three_are_inserted(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, BEFORE)
    assert _role_rows(engine) == ["trading"]

    command.upgrade(config, AFTER)

    assert _role_rows(engine) == sorted(FOUR_ROLES)


def test_running_the_migration_twice_neither_fails_nor_duplicates(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)

    command.downgrade(config, BEFORE)
    command.upgrade(config, AFTER)

    assert _role_rows(engine) == sorted(FOUR_ROLES)


def test_the_downgrade_removes_no_role_and_no_assignment(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (email, full_name, is_active) VALUES ('a@example.com', 'A', true)"))
        connection.execute(text(
            "INSERT INTO user_roles (user_id, role_id)"
            " SELECT u.id, r.id FROM users u, roles r WHERE u.email = 'a@example.com' AND r.name = 'finance'"
        ))

    command.downgrade(config, BEFORE)

    assert _role_rows(engine) == sorted(FOUR_ROLES)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM user_roles")).scalar() == 1


def test_a_later_insert_does_not_collide_with_a_role_stored_with_an_explicit_id(
    scratch: tuple[Config, Engine],
) -> None:
    config, engine = scratch
    command.upgrade(config, BEFORE)  # trading takes id 1 from the sequence
    with engine.begin() as connection:
        # As a restore would leave it: a row whose id the sequence has not handed out yet.
        connection.execute(text("INSERT INTO roles (id, name) VALUES (6, 'operations')"))

    command.upgrade(config, AFTER)

    with engine.begin() as connection:
        connection.execute(text("INSERT INTO roles (name) VALUES ('rol-de-prueba')"))
    assert "rol-de-prueba" in _role_rows(engine)


def test_the_development_seed_still_does_not_duplicate_the_roles(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, "head")

    with Session(engine) as session:
        seed(session, "dev@example.com")

    assert _role_rows(engine) == sorted(FOUR_ROLES)
