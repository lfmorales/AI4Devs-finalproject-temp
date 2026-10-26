"""The margin migration, run on a throwaway database that already holds campaign data.

Upgrade, `downgrade -1` and upgrade again must leave that data alone, and the btree_gist extension must be
removed only when the migration was the one that created it.
"""

from datetime import date
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL

BEFORE = "e6a29ae62e94"  # record the window of each ingestion batch
MARGIN = "439b6b8481f8"  # the migration under test
SCRATCH_DB = "adops360_margin_migration_test"
LIMITED_ROLE = "adops360_margin_limited"
MARGIN_TABLES = {"rebate_schedules", "rebate_brackets", "platform_rate_settings", "applied_rates", "applied_rate_brackets"}


def _admin():
    return create_engine(make_url(TEST_DATABASE_URL).set(database="postgres"), isolation_level="AUTOCOMMIT")


@pytest.fixture
def scratch(monkeypatch):
    """An empty database migrated to the revision before the margin tables, with data in it; dropped afterwards."""
    admin = _admin()
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
        _seed(connection)
    try:
        yield config, engine, url
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
            connection.execute(text(f"DROP ROLE IF EXISTS {LIMITED_ROLE}"))
        admin.dispose()


def _seed(connection) -> None:
    for table in ("holding_groups", "advertisers", "dsps", "channels", "formats", "campaign_types", "sectors", "sales_reps"):
        connection.execute(text(f"INSERT INTO {table} (name) VALUES ('fixture')"))
    connection.execute(text("INSERT INTO agencies (holding_group_id, name) VALUES (1, 'fixture')"))
    connection.execute(text(
        "INSERT INTO campaigns (name, display_name, agency_id, advertiser_id, campaign_type_id, sector_id, sales_rep_id,"
        " start_date, end_date) VALUES ('c', 'c', 1, 1, 1, 1, 1, '2026-08-01', '2026-08-31')"))
    connection.execute(text(
        "INSERT INTO campaign_periods (campaign_id, period_year, period_month, period_start, period_end)"
        " VALUES (1, 2026, 8, '2026-08-01', '2026-08-31')"))
    connection.execute(text(
        "INSERT INTO campaign_lines (campaign_id, line_number, start_date, end_date, dsp_id, channel_id, format_id, scope,"
        " market_description, contracted_impressions, sale_cpm) VALUES"
        " (1, 1, '2026-08-01', '2026-08-31', 1, 1, 1, 'national', 'x', 726202, 5.00)"))
    connection.execute(text(
        "INSERT INTO campaign_line_periods (campaign_line_id, campaign_period_id, flight_start, flight_end,"
        " contracted_impressions) VALUES (1, 1, '2026-08-01', '2026-08-31', 726202)"))
    connection.execute(text("INSERT INTO users (email, full_name, is_active) VALUES ('m@example.com', 'M', true)"))


def _tables(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _has_extension(engine) -> bool:
    with engine.connect() as connection:
        return bool(connection.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'btree_gist'")).scalar())


def _insert_margin_rows(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO rebate_schedules (holding_group_id, valid_from) VALUES (1, '2026-01-01')"))
        connection.execute(text(
            "INSERT INTO rebate_brackets (rebate_schedule_id, position, lower, upper, rate)"
            " VALUES (1, 1, 0, NULL, 0.25)"))
        connection.execute(text(
            "INSERT INTO applied_rates (campaign_line_period_id, rebate_schedule_id, ladder_step, agency_exception,"
            " effective_rate, counter_group_id, counter_channel_id, counter_year, position_before, position_after,"
            " rebate_amount, platform_rate, closed_at, closed_by) VALUES"
            " (1, 1, 6, false, 0.25, 1, 1, 2026, 0, 3631.01, 907.7525, 1.00, '2026-09-01 10:00', 1)"))


def test_upgrade_creates_the_margin_tables_and_the_system_rate_next_to_existing_data(scratch):
    config, engine, _ = scratch

    command.upgrade(config, "head")

    assert MARGIN_TABLES <= _tables(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM campaigns")).scalar() == 1
        rate = connection.execute(
            text("SELECT rate_per_thousand, created_by FROM platform_rate_settings WHERE level = 'system'")
        ).all()
    assert [(row[0], row[1]) for row in rate] == [(Decimal("1.000000"), None)]


def test_downgrade_one_step_drops_only_the_margin_tables_and_keeps_the_data(scratch):
    config, engine, _ = scratch
    command.upgrade(config, "head")
    _insert_margin_rows(engine)

    command.downgrade(config, "-1")

    assert not MARGIN_TABLES & _tables(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM campaigns")).scalar() == 1
        assert connection.execute(text("SELECT count(*) FROM campaign_line_periods")).scalar() == 1
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == BEFORE


def test_upgrade_again_after_a_downgrade_is_clean_and_seeds_the_system_rate_once(scratch):
    config, engine, _ = scratch
    command.upgrade(config, "head")
    command.downgrade(config, "-1")

    command.upgrade(config, "head")

    assert MARGIN_TABLES <= _tables(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM platform_rate_settings WHERE level = 'system'")).scalar() == 1


def test_the_extension_is_removed_on_downgrade_when_the_migration_created_it(scratch):
    config, engine, _ = scratch
    assert not _has_extension(engine)

    command.upgrade(config, "head")
    assert _has_extension(engine)
    command.downgrade(config, "-1")

    assert not _has_extension(engine)


def test_the_extension_is_kept_on_downgrade_when_it_already_existed(scratch):
    config, engine, _ = scratch
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION btree_gist"))

    command.upgrade(config, "head")
    command.downgrade(config, "-1")

    assert _has_extension(engine)


def test_the_append_only_triggers_go_with_the_downgrade(scratch):
    config, engine, _ = scratch
    command.upgrade(config, "head")

    command.downgrade(config, "-1")

    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM pg_proc WHERE proname = 'reject_append_only_change'")).scalar() == 0


def test_without_the_privilege_the_migration_stops_with_a_message_that_says_what_to_do(scratch, monkeypatch):
    config, engine, url = scratch
    admin = _admin()
    with admin.connect() as connection:
        connection.execute(text(f"DROP ROLE IF EXISTS {LIMITED_ROLE}"))
        connection.execute(text(f"CREATE ROLE {LIMITED_ROLE} LOGIN PASSWORD 'limited' NOSUPERUSER"))
    with engine.begin() as connection:
        connection.execute(text(f'REVOKE CREATE ON DATABASE "{SCRATCH_DB}" FROM PUBLIC'))
        connection.execute(text(f"GRANT ALL ON SCHEMA public TO {LIMITED_ROLE}"))
        connection.execute(text(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {LIMITED_ROLE}"))
        connection.execute(text(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {LIMITED_ROLE}"))
    limited = url.set(username=LIMITED_ROLE, password="limited")
    monkeypatch.setenv("DATABASE_URL", limited.render_as_string(hide_password=False))

    with pytest.raises(RuntimeError) as raised:
        command.upgrade(config, "head")

    assert "btree_gist" in str(raised.value)
    assert "CREATE EXTENSION btree_gist" in str(raised.value)
    assert "docs/deploy.md" in str(raised.value)
    assert not MARGIN_TABLES & _tables(engine)
    admin.dispose()
