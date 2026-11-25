"""The migration that adds the closing headers, their batches and the snapshot of every closed flight.

It refuses a database that already holds closed flights: their snapshot cannot be rebuilt, because the delivery of the
moment they were closed is no longer stored, and there is no production to keep. On a database without closed flights
it creates the three tables, all append-only, with every column required except the gross of a committed flight.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL

BEFORE = "950895fa2d75"  # add the frozen revenue and rebate base to the applied rates
AFTER = "3a08cce1c979"  # the migration under test; later migrations are not part of these tests
SCRATCH_DB = "adops360_closing_snapshot_migration_test"
TABLES = ("month_closings", "month_closing_batches", "closed_flight_snapshots")
NULLABLE = {"closed_flight_snapshots": {"gross_revenue"}}


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


def _snapshot_sql(gross: str = "NULL", commitment: str = "'committed'", metric: str = "'impressions'") -> str:
    return (
        "INSERT INTO closed_flight_snapshots (applied_rate_id, month_closing_id, revenue, contracted_revenue,"
        " media_cost, rebate, platform_cost, margin, gross_revenue, delivered_impressions, delivered, window_media_cost,"
        " window_reported_revenue, window_buyer_spend, window_data_cost, gross_differs_from_buyer_spend,"
        " data_cost_reported, delivery_metric, sale_cpm, contracted_impressions, volume_commitment) VALUES"
        f" (1, 1, 5000.00, 5000.00, 1200.00, 0.00, 700.00, 3100.00, {gross}, 700000, 700000.0000, 1200.000000,"
        f" 0, 0, 0, false, false, {metric}, 5.00, 1000000, {commitment})"
    )


def _closed(engine: Engine) -> None:
    """The seeded flight closed with its header, ready for one snapshot."""
    with engine.begin() as connection:
        _close_the_flight(connection)
        _add_header(connection)


def _tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _columns(engine: Engine, table: str) -> dict[str, Any]:
    return {column["name"]: column for column in inspect(engine).get_columns(table)}


# ---------------------------------------------------------------- the refusal
def test_a_database_holding_a_closed_flight_is_refused_with_the_reset_command(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    with engine.begin() as connection:
        _close_the_flight(connection)

    with pytest.raises(RuntimeError, match=r"e2e/scripts/reset-data\.sh"):
        command.upgrade(config, AFTER)

    assert not set(TABLES) & _tables(engine)
    assert _revision(engine) == BEFORE


# ---------------------------------------------------------------- the tables
def test_without_closed_flights_it_creates_the_three_tables(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch

    command.upgrade(config, AFTER)

    assert set(TABLES) <= _tables(engine)


@pytest.mark.parametrize("table", TABLES)
def test_every_column_is_required_except_the_gross(scratch: tuple[Config, Engine], table: str) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)

    nullable = {name for name, column in _columns(engine, table).items() if column["nullable"]}

    assert nullable == NULLABLE.get(table, set())


@pytest.mark.parametrize("table", TABLES)
def test_no_column_is_floating_point(scratch: tuple[Config, Engine], table: str) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)

    for name, column in _columns(engine, table).items():
        assert column["type"].__class__.__name__ not in {"FLOAT", "REAL", "DOUBLE_PRECISION"}, name


def test_the_amounts_have_two_decimals_and_the_window_sums_the_precision_of_the_delivery(
    scratch: tuple[Config, Engine],
) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)

    columns = _columns(engine, "closed_flight_snapshots")
    for name in ("revenue", "contracted_revenue", "media_cost", "rebate", "platform_cost", "margin", "gross_revenue"):
        assert (columns[name]["type"].precision, columns[name]["type"].scale) == (18, 2), name
    for name in ("window_media_cost", "window_reported_revenue", "window_buyer_spend", "window_data_cost"):
        assert (columns[name]["type"].precision, columns[name]["type"].scale) == (18, 6), name
    assert (columns["delivered"]["type"].precision, columns["delivered"]["type"].scale) == (18, 4)


def test_a_committed_snapshot_without_a_gross_is_stored(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    _closed(engine)

    with engine.begin() as connection:
        connection.execute(text(_snapshot_sql()))
        stored = connection.execute(text("SELECT margin, gross_revenue FROM closed_flight_snapshots")).one()

    assert (str(stored[0]), stored[1]) == ("3100.00", None)


@pytest.mark.parametrize(
    ("gross", "commitment"),
    [("5500.00", "'committed'"), ("NULL", "'target'")],
    ids=["a committed flight with a gross", "a target flight without one"],
)
def test_the_gross_goes_with_a_target_flight_and_only_with_one(
    scratch: tuple[Config, Engine], gross: str, commitment: str
) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    _closed(engine)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(_snapshot_sql(gross=gross, commitment=commitment)))


def test_a_target_snapshot_with_its_gross_is_stored(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    _closed(engine)

    with engine.begin() as connection:
        connection.execute(text(_snapshot_sql(gross="5500.00", commitment="'target'")))


@pytest.mark.parametrize(
    "values", [{"metric": "'clicks'"}, {"commitment": "'guaranteed'"}], ids=["an unknown metric", "an unknown commitment"]
)
def test_the_metric_and_the_commitment_refuse_other_values(
    scratch: tuple[Config, Engine], values: dict[str, str]
) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    _closed(engine)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(_snapshot_sql(**values)))


def test_an_applied_rate_row_has_at_most_one_snapshot(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    _closed(engine)
    with engine.begin() as connection:
        connection.execute(text(_snapshot_sql()))

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(_snapshot_sql()))


def test_a_header_names_one_batch_per_dsp(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    _closed(engine)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO month_closing_batches (month_closing_id, dsp_id, ingestion_batch_id) VALUES (1, 1, 1)"))


def test_a_month_may_hold_several_headers(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    _closed(engine)

    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO month_closings (period_year, period_month, closed_at, closed_by, as_of)"
            " VALUES (2026, 8, '2026-09-10 12:00', 1, '2026-09-09')"))
        count = connection.execute(text("SELECT count(*) FROM month_closings WHERE period_month = 8")).scalar()

    assert count == 2


@pytest.mark.parametrize("statement", ["UPDATE {table} SET month_closing_id = month_closing_id", "DELETE FROM {table}"])
@pytest.mark.parametrize("table", TABLES)
def test_the_three_tables_are_append_only(scratch: tuple[Config, Engine], table: str, statement: str) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    _closed(engine)
    with engine.begin() as connection:
        connection.execute(text(_snapshot_sql()))
    sql = statement.format(table=table)
    if table == "month_closings":
        sql = sql.replace("month_closing_id = month_closing_id", "as_of = as_of")

    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(text(sql))


# ---------------------------------------------------------------- downgrade and history
def test_downgrade_drops_the_three_tables_and_keeps_the_rates(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    _closed(engine)
    with engine.begin() as connection:
        connection.execute(text(_snapshot_sql()))

    command.downgrade(config, "-1")

    assert not set(TABLES) & _tables(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM applied_rates")).scalar() == 1


def test_the_migration_hangs_from_the_frozen_revenue_migration_and_the_history_has_one_head(
    scratch: tuple[Config, Engine],
) -> None:
    config, _ = scratch
    script = ScriptDirectory.from_config(config)

    assert script.get_revision(AFTER).down_revision == BEFORE
    assert len(script.get_heads()) == 1
