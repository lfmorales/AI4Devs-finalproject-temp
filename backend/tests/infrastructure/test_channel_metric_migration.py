"""The migration that adds the channel's delivery metric, on a database that already holds channels.

`DOOH` becomes `ots`, every other channel `impressions`; `downgrade -1` drops the column and upgrade restores it.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url

from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL

BEFORE = "f00c04503af9"  # add ots and video completions to the daily deliveries
AFTER = "8010208e4c15"  # the migration under test; later migrations are not part of these tests
SCRATCH_DB = "adops360_channel_metric_migration_test"


@pytest.fixture
def scratch(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Config, Engine]]:
    """A database migrated to the revision before the migration, holding DOOH, Directo and DEMO Channel."""
    admin = create_engine(make_url(TEST_DATABASE_URL).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    url = make_url(TEST_DATABASE_URL).set(database=SCRATCH_DB)
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, BEFORE)
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO channels (name) VALUES ('DOOH'), ('Directo'), ('DEMO Channel')"))
    try:
        yield config, engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def _metrics(engine: Engine) -> dict[str, str]:
    with engine.connect() as connection:
        return dict(connection.execute(text("SELECT name, delivery_metric FROM channels")).tuples().all())


def _has_column(engine: Engine) -> bool:
    return "delivery_metric" in {column["name"] for column in inspect(engine).get_columns("channels")}


def test_the_column_does_not_exist_before_the_migration(scratch: tuple[Config, Engine]) -> None:
    _, engine = scratch

    assert not _has_column(engine)


def test_dooh_becomes_ots_and_every_other_channel_impressions(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch

    command.upgrade(config, AFTER)

    assert _metrics(engine) == {"DOOH": "ots", "Directo": "impressions", "DEMO Channel": "impressions"}


def test_the_column_is_not_null_with_an_impressions_default(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch

    command.upgrade(config, AFTER)

    column = next(c for c in inspect(engine).get_columns("channels") if c["name"] == "delivery_metric")
    assert column["nullable"] is False
    assert "impressions" in str(column["default"])


def test_downgrade_drops_the_column_and_upgrade_restores_the_metrics(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)

    command.downgrade(config, "-1")
    assert not _has_column(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM channels")).scalar() == 3

    command.upgrade(config, AFTER)
    assert _metrics(engine) == {"DOOH": "ots", "Directo": "impressions", "DEMO Channel": "impressions"}


def test_a_database_without_a_dooh_channel_upgrades_with_every_channel_on_impressions(
    scratch: tuple[Config, Engine],
) -> None:
    config, engine = scratch
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM channels WHERE name = 'DOOH'"))

    command.upgrade(config, AFTER)

    assert set(_metrics(engine).values()) == {"impressions"}


def test_the_migration_hangs_from_the_deliveries_migration_and_the_history_has_one_head(
    scratch: tuple[Config, Engine],
) -> None:
    config, _ = scratch
    script = ScriptDirectory.from_config(config)

    assert script.get_revision(AFTER).down_revision == BEFORE
    assert len(script.get_heads()) == 1
