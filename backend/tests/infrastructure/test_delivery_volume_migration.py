"""The migration that adds OTS and video completions to the daily deliveries, on a database holding delivery rows.

Upgrade, `downgrade -1` and upgrade again must leave the existing rows alone: they read 0.0000 OTS and 0 completions.
"""

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, Row, create_engine, inspect, text
from sqlalchemy.engine import make_url

from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL

BEFORE = "e5d42817a180"  # insert the four roles
AFTER = "f00c04503af9"  # the migration under test; later migrations are not part of these tests
SCRATCH_DB = "adops360_delivery_volume_migration_test"
NEW_COLUMNS = {"ots", "video_completions"}


@pytest.fixture
def scratch(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Config, Engine]]:
    """A database migrated to the revision before the migration, holding one delivery row; dropped afterwards."""
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
        _seed_one_delivery(connection)
    try:
        yield config, engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def _seed_one_delivery(connection: Connection) -> None:
    for table in ("holding_groups", "advertisers", "dsps", "channels", "formats", "campaign_types", "sectors", "sales_reps"):
        connection.execute(text(f"INSERT INTO {table} (name) VALUES ('fixture')"))
    connection.execute(text("INSERT INTO agencies (holding_group_id, name) VALUES (1, 'fixture')"))
    connection.execute(text(
        "INSERT INTO campaigns (name, display_name, agency_id, advertiser_id, campaign_type_id, sector_id, sales_rep_id,"
        " start_date, end_date) VALUES ('c', 'c', 1, 1, 1, 1, 1, '2026-08-01', '2026-08-31')"))
    connection.execute(text(
        "INSERT INTO campaign_lines (campaign_id, line_number, start_date, end_date, dsp_id, channel_id, format_id, scope,"
        " market_description, contracted_impressions, sale_cpm) VALUES"
        " (1, 1, '2026-08-01', '2026-08-31', 1, 1, 1, 'national', 'x', 726202, 5.00)"))
    connection.execute(text(
        "INSERT INTO ingestion_batches (dsp_id, route, started_at, status, row_count, window_start, window_end)"
        " VALUES (1, 'api', '2026-08-04 02:00', 'succeeded', 1, '2026-08-01', '2026-08-31')"))
    connection.execute(text(
        "INSERT INTO daily_deliveries (campaign_line_id, ingestion_batch_id, delivery_date, impressions, clicks,"
        " media_cost, measurable_impressions, viewable_impressions) VALUES (1, 1, '2026-08-03', 1000, 10, 5.5, 900, 700)"))


def _columns(engine: Engine) -> dict[str, Any]:
    return {column["name"]: column for column in inspect(engine).get_columns("daily_deliveries")}


def _delivery(engine: Engine) -> Row[Any]:
    with engine.connect() as connection:
        return connection.execute(text(
            "SELECT impressions, media_cost, {} FROM daily_deliveries".format("ots, video_completions")
            if NEW_COLUMNS <= set(_columns(engine)) else "SELECT impressions, media_cost FROM daily_deliveries"
        )).one()


def test_the_columns_do_not_exist_before_the_migration(scratch: tuple[Config, Engine]) -> None:
    _, engine = scratch

    assert not NEW_COLUMNS & set(_columns(engine))


def test_the_migration_hangs_from_the_roles_revision_and_adds_two_not_null_columns_defaulting_to_zero(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch

    command.upgrade(config, AFTER)

    columns = _columns(engine)
    assert (columns["ots"]["type"].precision, columns["ots"]["type"].scale) == (18, 4)
    assert columns["video_completions"]["type"].__class__.__name__ == "BIGINT"
    assert (columns["ots"]["nullable"], columns["video_completions"]["nullable"]) == (False, False)
    assert (columns["ots"]["default"], columns["video_completions"]["default"]) == ("0", "0")


def test_the_existing_row_reads_zero_ots_and_zero_completions_and_keeps_the_rest(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch

    command.upgrade(config, AFTER)

    assert tuple(_delivery(engine)) == (1000, Decimal("5.500000"), Decimal("0.0000"), 0)


def test_downgrade_removes_the_columns_and_keeps_the_row_and_upgrade_restores_them(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)

    command.downgrade(config, "-1")
    assert not NEW_COLUMNS & set(_columns(engine))
    assert tuple(_delivery(engine)) == (1000, Decimal("5.500000"))

    command.upgrade(config, AFTER)
    assert tuple(_delivery(engine)) == (1000, Decimal("5.500000"), Decimal("0.0000"), 0)


def test_the_down_revision_is_the_roles_migration_and_the_history_has_one_head(scratch: tuple[Config, Engine]) -> None:
    from alembic.script import ScriptDirectory

    config, _ = scratch
    script = ScriptDirectory.from_config(config)

    assert script.get_revision(AFTER).down_revision == BEFORE
    assert len(script.get_heads()) == 1
