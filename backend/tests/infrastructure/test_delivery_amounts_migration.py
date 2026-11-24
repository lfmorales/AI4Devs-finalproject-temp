"""The migration that adds the four reported amounts to the daily deliveries, on a database that already holds one.

The existing row reads zero in the four and keeps the rest; `downgrade -1` drops them and upgrade restores the zeros.
"""

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url

from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL

BEFORE = "273c50da57b0"  # add the volume commitment to the campaign lines
AFTER = "763931a4d704"  # the migration under test; later migrations are not part of these tests
SCRATCH_DB = "adops360_delivery_amounts_migration_test"
AMOUNTS = ("buyer_spend", "reported_revenue", "third_party_data_cost", "audience_data_cost")


@pytest.fixture
def scratch(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Config, Engine]]:
    """A database migrated to the revision before the migration, holding one Adform delivery row."""
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
        " start_date, end_date) VALUES ('c', 'c', 1, 1, 1, 1, 1, '2026-11-01', '2026-11-30')"))
    connection.execute(text(
        "INSERT INTO campaign_lines (campaign_id, line_number, start_date, end_date, dsp_id, channel_id, format_id, scope,"
        " market_description, contracted_impressions, sale_cpm) VALUES"
        " (1, 1, '2026-11-01', '2026-11-30', 1, 1, 1, 'national', 'x', 1000000, 5.00)"))
    connection.execute(text(
        "INSERT INTO ingestion_batches (dsp_id, route, started_at, status, row_count, window_start, window_end)"
        " VALUES (1, 'api', '2026-11-20 02:00', 'succeeded', 1, '2026-11-13', '2026-11-19')"))
    connection.execute(text(
        "INSERT INTO daily_deliveries (campaign_line_id, ingestion_batch_id, delivery_date, impressions, clicks,"
        " media_cost, measurable_impressions, viewable_impressions) VALUES (1, 1, '2026-11-19', 1000, 10, 5.5, 900, 700)"))


def _columns(engine: Engine) -> dict[str, Any]:
    return {column["name"]: column for column in inspect(engine).get_columns("daily_deliveries")}


def _row(engine: Engine) -> tuple[Any, ...]:
    present = [name for name in AMOUNTS if name in _columns(engine)]
    with engine.connect() as connection:
        return tuple(connection.execute(
            text(f"SELECT {', '.join(['impressions', 'media_cost', *present])} FROM daily_deliveries")
        ).one())


def test_the_columns_do_not_exist_before_the_migration(scratch: tuple[Config, Engine]) -> None:
    _, engine = scratch

    assert not set(AMOUNTS) & set(_columns(engine))


def test_the_four_columns_are_not_null_six_decimal_numbers_defaulting_to_zero(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch

    command.upgrade(config, AFTER)

    columns = _columns(engine)
    for name in AMOUNTS:
        assert (columns[name]["type"].precision, columns[name]["type"].scale) == (18, 6), name
        assert (columns[name]["nullable"], columns[name]["default"]) == (False, "0"), name


def test_the_existing_row_reads_zero_in_the_four_and_keeps_the_rest(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch

    command.upgrade(config, AFTER)

    assert _row(engine) == (1000, Decimal("5.500000"), *([Decimal("0.000000")] * 4))


def test_downgrade_removes_the_columns_and_keeps_the_row_and_upgrade_restores_the_zeros(
    scratch: tuple[Config, Engine],
) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)

    command.downgrade(config, "-1")
    assert not set(AMOUNTS) & set(_columns(engine))
    assert _row(engine) == (1000, Decimal("5.500000"))

    command.upgrade(config, AFTER)
    assert _row(engine) == (1000, Decimal("5.500000"), *([Decimal("0.000000")] * 4))


def test_the_migration_hangs_from_the_volume_commitment_migration_and_the_history_has_one_head(
    scratch: tuple[Config, Engine],
) -> None:
    config, _ = scratch
    script = ScriptDirectory.from_config(config)

    assert script.get_revision(AFTER).down_revision == BEFORE
    assert len(script.get_heads()) == 1
