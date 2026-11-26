"""The migration that adds the billing a closing freezes to the snapshot of every closed flight.

The snapshot gains the billing basis, the billable volume, the carry-over and whether it was billable, and the adjustment
in force (committed-billing-and-review). A snapshot written before this migration keeps all of them null, together: its
flight keeps the revenue it was closed with. A target flight's basis is `reported`; a committed one's never is.
"""

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL

BEFORE = "e8b5c3a07f24"  # add the review events of a campaign in a month
AFTER = "f1c6d2b84a57"  # the migration under test; later migrations are not part of these tests
SCRATCH_DB = "adops360_billing_snapshot_migration_test"
TABLE = "closed_flight_snapshots"
COLUMNS = ("billing_basis", "billable", "carryover", "carryover_billable", "billing_adjustment_id")


@pytest.fixture
def scratch(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Config, Engine]]:
    """A database migrated to the revision before the migration, holding one ended flight and no closed flight."""
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
        _seed_one_ended_flight(connection)
    try:
        yield config, engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def _seed_one_ended_flight(connection: Connection) -> None:
    for table in ("holding_groups", "advertisers", "dsps", "channels", "formats", "campaign_types", "sectors", "sales_reps"):
        connection.execute(text(f"INSERT INTO {table} (name) VALUES ('fixture')"))
    connection.execute(text("INSERT INTO agencies (holding_group_id, name) VALUES (1, 'fixture')"))
    connection.execute(text(
        "INSERT INTO campaigns (name, display_name, agency_id, advertiser_id, campaign_type_id, sector_id, sales_rep_id,"
        " start_date, end_date) VALUES ('c', 'c', 1, 1, 1, 1, 1, '2026-08-01', '2026-08-31')"))
    connection.execute(text(
        "INSERT INTO campaign_lines (campaign_id, line_number, start_date, end_date, dsp_id, channel_id, format_id, scope,"
        " market_description, contracted_impressions, sale_cpm) VALUES"
        " (1, 1, '2026-08-01', '2026-08-31', 1, 1, 1, 'national', 'x', 1000000, 5.00)"))
    connection.execute(text(
        "INSERT INTO campaign_periods (campaign_id, period_year, period_month, period_start, period_end)"
        " VALUES (1, 2026, 8, '2026-08-01', '2026-08-31')"))
    connection.execute(text(
        "INSERT INTO campaign_line_periods (campaign_line_id, campaign_period_id, flight_start, flight_end,"
        " contracted_impressions) VALUES (1, 1, '2026-08-01', '2026-08-31', 1000000)"))
    connection.execute(text(
        "INSERT INTO users (email, full_name, is_active) VALUES ('migration@example.com', 'Migration', true)"))
    connection.execute(text(
        "INSERT INTO ingestion_batches (dsp_id, route, started_at, finished_at, window_start, window_end, status,"
        " row_count) VALUES (1, 'api', '2026-09-01 02:00', '2026-09-01 02:05', '2026-08-25', '2026-08-31',"
        " 'succeeded', 7)"))


def _close_the_flight(connection: Connection) -> None:
    """The rates row the closing writes for the seeded flight: a committed flight priced with no schedule."""
    connection.execute(text(
        "INSERT INTO applied_rates (campaign_line_period_id, ladder_step, agency_exception, zero_reason, effective_rate,"
        " counter_group_id, counter_channel_id, counter_year, position_before, position_after, rebate_amount,"
        " platform_rate, closed_at, closed_by) VALUES"
        " (1, 8, false, 'no_schedule', 0, 1, 1, 2026, 0, 5000, 0, 1.00, '2026-09-01 12:00', 1)"))


def _add_header(connection: Connection) -> None:
    connection.execute(text(
        "INSERT INTO month_closings (period_year, period_month, closed_at, closed_by, as_of)"
        " VALUES (2026, 8, '2026-09-01 12:00', 1, '2026-08-31')"))
    connection.execute(text(
        "INSERT INTO month_closing_batches (month_closing_id, dsp_id, ingestion_batch_id) VALUES (1, 1, 1)"))


def _snapshot_sql(
    basis: str = "'minimum'", billable: str = "700000", carryover: str = "0", billable_flag: str = "false",
    adjustment: str = "NULL", commitment: str = "'committed'", gross: str = "NULL",
) -> str:
    return (
        "INSERT INTO closed_flight_snapshots (applied_rate_id, month_closing_id, revenue, contracted_revenue,"
        " media_cost, rebate, platform_cost, margin, gross_revenue, delivered_impressions, delivered, window_media_cost,"
        " window_reported_revenue, window_buyer_spend, window_data_cost, gross_differs_from_buyer_spend,"
        " data_cost_reported, delivery_metric, sale_cpm, contracted_impressions, volume_commitment, billing_basis,"
        " billable, carryover, carryover_billable, billing_adjustment_id) VALUES"
        f" (1, 1, 3500.00, 5000.00, 1200.00, 875.00, 700.00, 725.00, {gross}, 700000, 700000.0000, 1200.000000,"
        f" 0, 0, 0, false, false, 'impressions', 5.00, 1000000, {commitment}, {basis}, {billable}, {carryover},"
        f" {billable_flag}, {adjustment})"
    )


def _legacy_snapshot_sql() -> str:
    """A snapshot as the closing wrote it before this migration: no billing column."""
    return (
        "INSERT INTO closed_flight_snapshots (applied_rate_id, month_closing_id, revenue, contracted_revenue,"
        " media_cost, rebate, platform_cost, margin, gross_revenue, delivered_impressions, delivered, window_media_cost,"
        " window_reported_revenue, window_buyer_spend, window_data_cost, gross_differs_from_buyer_spend,"
        " data_cost_reported, delivery_metric, sale_cpm, contracted_impressions, volume_commitment) VALUES"
        " (1, 1, 5000.00, 5000.00, 1200.00, 1250.00, 700.00, 1850.00, NULL, 700000, 700000.0000, 1200.000000,"
        " 0, 0, 0, false, false, 'impressions', 5.00, 1000000, 'committed')"
    )


def _closed(engine: Engine) -> None:
    with engine.begin() as connection:
        _close_the_flight(connection)
        _add_header(connection)


def _adjustment(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO flight_billing_adjustments (campaign_line_period_id, basis, amount, reason, created_by)"
            " VALUES (1, 'custom', 4200.00, 'Acuerdo', 1)"))


def _insert(engine: Engine, sql: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(sql))


def _columns(engine: Engine) -> dict[str, Any]:
    return {column["name"]: column for column in inspect(engine).get_columns(TABLE)}


def _revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


@pytest.fixture
def migrated(scratch: tuple[Config, Engine]) -> Engine:
    config, engine = scratch
    command.upgrade(config, AFTER)
    _closed(engine)
    return engine


# ---------------------------------------------------------------- the columns


def test_the_five_columns_are_added_and_they_are_all_optional(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    before = set(_columns(engine))

    command.upgrade(config, AFTER)

    columns = _columns(engine)
    assert set(columns) - before == set(COLUMNS)
    assert all(columns[name]["nullable"] for name in COLUMNS)


def test_the_types_follow_the_rest_of_the_snapshot(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    columns = _columns(engine)

    assert str(columns["billable"]["type"]) == "NUMERIC(18, 4)"
    assert str(columns["carryover"]["type"]) == "BIGINT"
    assert str(columns["carryover_billable"]["type"]) == "BOOLEAN"
    assert not [name for name in COLUMNS if "FLOAT" in str(columns[name]["type"]).upper()]


def test_a_snapshot_written_before_the_migration_keeps_every_billing_column_null(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    _closed(engine)
    _insert(engine, _legacy_snapshot_sql())

    command.upgrade(config, AFTER)

    with engine.connect() as connection:
        row = connection.execute(text(f"SELECT revenue, {', '.join(COLUMNS)} FROM {TABLE}")).one()
    assert tuple(row) == (Decimal("5000.00"), None, None, None, None, None)


def test_a_database_with_closed_flights_is_migrated(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    _closed(engine)
    _insert(engine, _legacy_snapshot_sql())

    command.upgrade(config, AFTER)

    assert _revision(engine) == AFTER


# ---------------------------------------------------------------- what the database accepts and refuses


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"basis": "'delivered'", "adjustment": "1"},
        {"basis": "'contracted'", "billable": "1000000", "adjustment": "1"},
        {"basis": "'custom'", "billable": "NULL", "adjustment": "1"},
        {"basis": "'minimum'", "adjustment": "1"},
        {"carryover": "100000", "billable_flag": "true"},
        {"basis": "'reported'", "billable": "NULL", "commitment": "'target'", "gross": "5500.00"},
    ],
    ids=["minimum", "delivered", "contracted", "custom", "minimum-adjusted", "billable-carry-over", "target"],
)
def test_a_snapshot_with_its_billing_is_stored(migrated: Engine, values: dict[str, str]) -> None:
    _adjustment(migrated)

    _insert(migrated, _snapshot_sql(**values))


@pytest.mark.parametrize(
    "values",
    [
        {"basis": "NULL"},
        {"carryover": "NULL"},
        {"billable_flag": "NULL"},
        {"basis": "'other'"},
        {"basis": "'reported'", "billable": "NULL"},
        {"commitment": "'target'", "gross": "5500.00"},
        {"basis": "'custom'", "adjustment": "1"},
        {"basis": "'reported'", "billable": "700000", "commitment": "'target'", "gross": "5500.00"},
        {"basis": "'delivered'"},
        {"basis": "'contracted'"},
        {"basis": "'custom'", "billable": "NULL"},
        {"carryover": "-1"},
        {"adjustment": "999"},
    ],
    ids=["basis-missing", "carry-over-missing", "flag-missing", "unknown-basis", "reported-on-committed",
         "target-not-reported", "custom-with-billable", "reported-with-billable", "delivered-without-adjustment",
         "contracted-without-adjustment", "custom-without-adjustment", "negative-carry-over", "unknown-adjustment"],
)
def test_a_snapshot_whose_billing_does_not_hold_together_is_refused(migrated: Engine, values: dict[str, str]) -> None:
    _adjustment(migrated)

    with pytest.raises(IntegrityError):
        _insert(migrated, _snapshot_sql(**values))


# ---------------------------------------------------------------- downgrade and history


def test_downgrade_drops_the_five_columns_and_keeps_the_snapshots(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    _closed(engine)
    _insert(engine, _snapshot_sql())

    command.downgrade(config, "-1")

    assert not set(COLUMNS) & set(_columns(engine))
    assert _revision(engine) == BEFORE
    with engine.connect() as connection:
        assert connection.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar() == 1


def test_the_migration_hangs_from_the_reviews_migration_and_the_history_has_one_head(
    scratch: tuple[Config, Engine],
) -> None:
    config, _ = scratch
    script = ScriptDirectory.from_config(config)

    assert script.get_revision(AFTER).down_revision == BEFORE
    assert len(script.get_heads()) == 1
