"""The migration that adds the line's volume commitment, on a database that already holds a line.

The existing line becomes `committed`; the check refuses any other value but `target`; `downgrade -1` drops the
column and upgrade restores it.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL

BEFORE = "8010208e4c15"  # add the delivery metric to the channels
AFTER = "273c50da57b0"  # the migration under test; later migrations are not part of these tests
SCRATCH_DB = "adops360_volume_commitment_migration_test"


@pytest.fixture
def scratch(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Config, Engine]]:
    """A database migrated to the revision before the migration, holding one campaign with one line."""
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
        _seed_line(connection)
    try:
        yield config, engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def _seed_line(connection) -> None:  # type: ignore[no-untyped-def]
    for table in ("holding_groups", "advertisers", "dsps", "channels", "formats", "campaign_types", "sectors", "sales_reps"):
        connection.execute(text(f"INSERT INTO {table} (name) VALUES ('fixture')"))
    connection.execute(text("INSERT INTO agencies (holding_group_id, name) VALUES (1, 'fixture')"))
    connection.execute(text(
        "INSERT INTO campaigns (name, display_name, agency_id, advertiser_id, campaign_type_id, sector_id, sales_rep_id,"
        " start_date, end_date) VALUES ('c', 'c', 1, 1, 1, 1, 1, '2026-11-01', '2026-11-30')"))
    connection.execute(text(
        "INSERT INTO campaign_lines (campaign_id, line_number, start_date, end_date, dsp_id, channel_id, format_id,"
        " scope, market_description, contracted_impressions, sale_cpm) VALUES"
        " (1, 1, '2026-11-01', '2026-11-30', 1, 1, 1, 'national', 'x', 1000000, 5.00)"))


def _commitments(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return list(connection.execute(text("SELECT volume_commitment FROM campaign_lines ORDER BY id")).scalars())


def _has_column(engine: Engine) -> bool:
    return "volume_commitment" in {column["name"] for column in inspect(engine).get_columns("campaign_lines")}


def test_the_column_does_not_exist_before_the_migration(scratch: tuple[Config, Engine]) -> None:
    _, engine = scratch

    assert not _has_column(engine)


def test_the_existing_line_becomes_committed(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch

    command.upgrade(config, AFTER)

    assert _commitments(engine) == ["committed"]


def test_the_column_is_not_null_with_a_committed_default(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch

    command.upgrade(config, AFTER)

    column = next(c for c in inspect(engine).get_columns("campaign_lines") if c["name"] == "volume_commitment")
    assert column["nullable"] is False
    assert "committed" in str(column["default"])


def test_the_existing_line_can_become_a_target_and_nothing_else(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)

    with engine.begin() as connection:
        connection.execute(text("UPDATE campaign_lines SET volume_commitment = 'target'"))
    assert _commitments(engine) == ["target"]

    with pytest.raises(IntegrityError, match="ck_campaign_lines_volume_commitment"):
        with engine.begin() as connection:
            connection.execute(text("UPDATE campaign_lines SET volume_commitment = 'maybe'"))
    assert _commitments(engine) == ["target"]


def test_downgrade_drops_the_column_and_upgrade_restores_committed(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)

    command.downgrade(config, "-1")
    assert not _has_column(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM campaign_lines")).scalar() == 1

    command.upgrade(config, AFTER)
    assert _commitments(engine) == ["committed"]


def test_the_migration_hangs_from_the_delivery_metric_migration_and_the_history_has_one_head(
    scratch: tuple[Config, Engine],
) -> None:
    config, _ = scratch
    script = ScriptDirectory.from_config(config)

    assert script.get_revision(AFTER).down_revision == BEFORE
    assert len(script.get_heads()) == 1
