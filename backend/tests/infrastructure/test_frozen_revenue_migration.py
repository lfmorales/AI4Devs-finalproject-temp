"""The migration that adds the frozen revenue and rebate base to the applied rates, on a database already holding one.

The existing row, a committed flight frozen before this change, reads null in both and keeps the rest; the pair check
holds; `downgrade -1` drops them, keeping the row, and upgrade restores the nulls. The append-only trigger never fires.
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
from sqlalchemy.exc import IntegrityError

from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL

BEFORE = "763931a4d704"  # add the reported amounts to the daily deliveries
AFTER = "950895fa2d75"  # the migration under test; later migrations are not part of these tests
SCRATCH_DB = "adops360_frozen_revenue_migration_test"
FROZEN = ("revenue_amount", "rebate_base_amount")
PAIR_CHECK = "ck_applied_rates_frozen_revenue_and_base_together"


@pytest.fixture
def scratch(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Config, Engine]]:
    """A database migrated to the revision before the migration, holding one closed committed flight."""
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
        _seed_one_frozen_flight(connection)
    try:
        yield config, engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def _seed_one_frozen_flight(connection: Connection) -> None:
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
        "INSERT INTO campaign_periods (campaign_id, period_year, period_month, period_start, period_end)"
        " VALUES (1, 2026, 8, '2026-08-01', '2026-08-31')"))
    connection.execute(text(
        "INSERT INTO campaign_line_periods (campaign_line_id, campaign_period_id, flight_start, flight_end,"
        " contracted_impressions) VALUES (1, 1, '2026-08-01', '2026-08-31', 726202)"))
    connection.execute(text(
        "INSERT INTO users (email, full_name, is_active) VALUES ('migration@example.com', 'Migration', true)"))
    connection.execute(text(
        "INSERT INTO applied_rates (campaign_line_period_id, ladder_step, agency_exception, zero_reason, effective_rate,"
        " counter_group_id, counter_channel_id, counter_year, position_before, position_after, rebate_amount,"
        " platform_rate, closed_at, closed_by) VALUES"
        " (1, 8, false, 'no_schedule', 0, 1, 1, 2026, 0, 3631.01, 0, 1.00, '2026-09-01 12:00', 1)"))


def _columns(engine: Engine) -> dict[str, Any]:
    return {column["name"]: column for column in inspect(engine).get_columns("applied_rates")}


def _row(engine: Engine) -> tuple[Any, ...]:
    present = [name for name in FROZEN if name in _columns(engine)]
    with engine.connect() as connection:
        return tuple(connection.execute(
            text(f"SELECT {', '.join(['position_after', 'rebate_amount', *present])} FROM applied_rates")
        ).one())


def _checks(engine: Engine) -> set[str]:
    return {check["name"] for check in inspect(engine).get_check_constraints("applied_rates") if check["name"]}


def test_the_columns_do_not_exist_before_the_migration(scratch: tuple[Config, Engine]) -> None:
    _, engine = scratch

    assert not set(FROZEN) & set(_columns(engine))


def test_the_two_columns_are_nullable_exact_numerics_with_no_default(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch

    command.upgrade(config, AFTER)

    columns = _columns(engine)
    for name in FROZEN:
        assert (columns[name]["type"].precision, columns[name]["type"].scale) == (24, 12), name
        assert (columns[name]["nullable"], columns[name]["default"]) == (True, None), name
    assert PAIR_CHECK in _checks(engine)


def test_the_existing_row_reads_null_in_both_and_keeps_the_rest(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch

    command.upgrade(config, AFTER)

    assert _row(engine) == (Decimal("3631.010000000000"), Decimal("0E-12"), None, None)


def test_after_the_migration_a_row_with_only_one_of_the_two_is_refused(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO campaign_line_periods (campaign_line_id, campaign_period_id, flight_start, flight_end,"
            " contracted_impressions) VALUES (1, 1, '2026-08-01', '2026-08-15', 1000)"))
        connection.execute(text(
            "INSERT INTO applied_rates (campaign_line_period_id, ladder_step, agency_exception, zero_reason,"
            " effective_rate, counter_group_id, counter_channel_id, counter_year, position_before, position_after,"
            " rebate_amount, platform_rate, closed_at, closed_by, revenue_amount) VALUES"
            " (2, 8, false, 'no_schedule', 0, 1, 1, 2026, 0, 5, 0, 1.00, '2026-09-01 12:00', 1, 4400)"))


def test_downgrade_removes_the_columns_and_keeps_the_row_and_upgrade_restores_the_nulls(
    scratch: tuple[Config, Engine],
) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)

    command.downgrade(config, "-1")
    assert not set(FROZEN) & set(_columns(engine))
    assert PAIR_CHECK not in _checks(engine)
    assert _row(engine) == (Decimal("3631.010000000000"), Decimal("0E-12"))

    command.upgrade(config, AFTER)
    assert _row(engine) == (Decimal("3631.010000000000"), Decimal("0E-12"), None, None)
    assert PAIR_CHECK in _checks(engine)


def test_the_migration_hangs_from_the_reported_amounts_migration_and_the_history_has_one_head(
    scratch: tuple[Config, Engine],
) -> None:
    config, _ = scratch
    script = ScriptDirectory.from_config(config)

    assert script.get_revision(AFTER).down_revision == BEFORE
    assert len(script.get_heads()) == 1
