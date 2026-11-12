"""The migration that adds the trading role, run on a throwaway database."""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL

BEFORE = "e33b0a845ea3"  # add the identity link columns to users
AFTER = "35164f01d7a1"  # the migration under test
SCRATCH_DB = "adops360_trading_role_migration_test"


@pytest.fixture
def scratch(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Config, Engine]]:
    """An empty database migrated to the revision before the trading role; dropped afterwards."""
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
    try:
        yield config, engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def _role_names(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return set(connection.execute(text("SELECT name FROM roles")).scalars())


def test_the_migration_inserts_the_trading_role(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    assert "trading" not in _role_names(engine)

    command.upgrade(config, AFTER)

    assert "trading" in _role_names(engine)


def test_the_migration_does_not_fail_when_the_row_already_exists(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO roles (name) VALUES ('trading')"))

    command.upgrade(config, AFTER)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM roles WHERE name = 'trading'")).scalar() == 1


def test_the_downgrade_removes_the_assignments_and_then_the_role(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO roles (name) VALUES ('trading'), ('operations') ON CONFLICT (name) DO NOTHING"))
        connection.execute(text("INSERT INTO users (email, full_name, is_active) VALUES ('a@example.com', 'A', true)"))
        connection.execute(text(
            "INSERT INTO user_roles (user_id, role_id)"
            " SELECT u.id, r.id FROM users u, roles r WHERE u.email = 'a@example.com' AND r.name IN ('trading', 'operations')"
        ))

    command.downgrade(config, BEFORE)

    assert "trading" not in _role_names(engine)
    with engine.connect() as connection:
        remaining = connection.execute(text(
            "SELECT r.name FROM user_roles ur JOIN roles r ON r.id = ur.role_id"
        )).scalars().all()
        assert remaining == ["operations"]
        assert connection.execute(text("SELECT count(*) FROM users")).scalar() == 1
