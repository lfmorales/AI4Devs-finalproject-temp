"""The migration that makes lines hang from their campaign, run on a throwaway database holding real rows."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL

BEFORE = "3cd42e61ae55"  # add campaign line flights: lines still hang from a period
AFTER = "520fbde04e94"  # the migration under test: lines hang from the campaign
SCRATCH_DB = "adops360_line_model_migration_test"


@pytest.fixture
def scratch(monkeypatch):
    """An empty database, migrated to the revision before the cleanup; dropped afterwards."""
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


def _seed_campaign(connection, with_campaign_id: bool = True, with_flights: bool = True) -> dict[str, int]:
    """One campaign over August and September with a line and, optionally, two flights (inserted latest first)."""
    for table in ("holding_groups", "advertisers", "dsps", "channels", "formats", "campaign_types", "sectors", "sales_reps"):
        connection.execute(text(f"INSERT INTO {table} (name) VALUES ('fixture')"))
    connection.execute(text("INSERT INTO agencies (holding_group_id, name) VALUES (1, 'fixture')"))
    connection.execute(text(
        "INSERT INTO campaigns (name, display_name, agency_id, advertiser_id, campaign_type_id, sector_id, sales_rep_id,"
        " start_date, end_date) VALUES ('c', 'c', 1, 1, 1, 1, 1, '2026-08-01', '2026-09-30')"))
    connection.execute(text(
        "INSERT INTO campaign_periods (campaign_id, period_year, period_month, period_start, period_end) VALUES"
        " (1, 2026, 8, '2026-08-01', '2026-08-31'), (1, 2026, 9, '2026-09-01', '2026-09-30')"))
    connection.execute(text(
        "INSERT INTO campaign_lines (campaign_period_id, campaign_id, line_number, start_date, end_date, dsp_id,"
        " channel_id, format_id, scope, market_description, contracted_impressions, sale_cpm) VALUES"
        " (2, :campaign_id, 1, '2026-08-01', '2026-09-30', 1, 1, 1, 'national', 'x', 100, 5.00)"),
        {"campaign_id": 1 if with_campaign_id else None})
    if with_flights:
        # September first, so "the earliest flight" cannot be mistaken for "the first one inserted".
        connection.execute(text(
            "INSERT INTO campaign_line_periods (campaign_line_id, campaign_period_id, flight_start, flight_end,"
            " contracted_impressions) VALUES (1, 2, '2026-09-01', '2026-09-30', 50), (1, 1, '2026-08-01', '2026-08-31', 50)"))
    return {"august_period": 1, "september_period": 2}


def _line_columns(engine) -> dict[str, dict]:
    return {c["name"]: c for c in inspect(engine).get_columns("campaign_lines")}


def test_upgrade_makes_the_line_columns_mandatory_and_drops_the_period(scratch):
    config, engine = scratch
    with engine.begin() as connection:
        _seed_campaign(connection)

    command.upgrade(config, AFTER)

    columns = _line_columns(engine)
    assert "campaign_period_id" not in columns
    assert all(columns[name]["nullable"] is False for name in ("campaign_id", "line_number", "start_date", "end_date"))
    assert "ix_campaign_lines_campaign_period_id" not in {i["name"] for i in inspect(engine).get_indexes("campaign_lines")}
    assert not any("campaign_period_id" in fk["constrained_columns"] for fk in inspect(engine).get_foreign_keys("campaign_lines"))


def test_upgrade_keeps_the_rows_and_their_flights(scratch):
    config, engine = scratch
    with engine.begin() as connection:
        _seed_campaign(connection)

    command.upgrade(config, AFTER)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM campaign_lines")).scalar() == 1
        assert connection.execute(text("SELECT count(*) FROM campaign_line_periods")).scalar() == 2


def test_upgrade_refuses_a_line_without_a_campaign_and_says_to_recreate_the_database(scratch):
    config, engine = scratch
    with engine.begin() as connection:
        _seed_campaign(connection, with_campaign_id=False)

    with pytest.raises(RuntimeError, match="recreate the development database"):
        command.upgrade(config, AFTER)

    assert "campaign_period_id" in _line_columns(engine)  # nothing was changed


def test_downgrade_restores_the_period_of_the_earliest_flight(scratch):
    config, engine = scratch
    with engine.begin() as connection:
        periods = _seed_campaign(connection)
    command.upgrade(config, AFTER)

    command.downgrade(config, BEFORE)

    columns = _line_columns(engine)
    assert columns["campaign_period_id"]["nullable"] is False
    assert all(columns[name]["nullable"] is True for name in ("campaign_id", "line_number", "start_date", "end_date"))
    with engine.connect() as connection:
        restored = connection.execute(text("SELECT campaign_period_id FROM campaign_lines")).scalar()
    assert restored == periods["august_period"]
    assert "ix_campaign_lines_campaign_period_id" in {i["name"] for i in inspect(engine).get_indexes("campaign_lines")}
    assert any(fk["constrained_columns"] == ["campaign_period_id"] for fk in inspect(engine).get_foreign_keys("campaign_lines"))


def test_downgrade_refuses_a_line_without_flights(scratch):
    config, engine = scratch
    with engine.begin() as connection:
        _seed_campaign(connection, with_flights=False)
    command.upgrade(config, AFTER)

    with pytest.raises(RuntimeError, match="no flights"):
        command.downgrade(config, BEFORE)

    assert "campaign_period_id" not in _line_columns(engine)  # nothing was changed


def test_upgrade_downgrade_upgrade_runs_clean(scratch):
    config, engine = scratch
    with engine.begin() as connection:
        _seed_campaign(connection)

    command.upgrade(config, AFTER)
    command.downgrade(config, BEFORE)
    command.upgrade(config, AFTER)

    assert "campaign_period_id" not in _line_columns(engine)
