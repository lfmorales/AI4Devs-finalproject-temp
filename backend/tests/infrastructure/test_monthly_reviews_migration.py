"""The migration that adds the review events of a campaign in a month (finance/monthly-review).

Only the events are stored, and only added: the state of a campaign is derived. A review has no cause; a reopening has
one, and the three edits that reopen a review (an adjustment, a carry-over, its billable flag) name the flight they
changed, which a withdrawal does not.
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

BEFORE = "d7e2a9f41b36"  # add the billing adjustments of a flight
AFTER = "e8b5c3a07f24"  # the migration under test; later migrations are not part of these tests
SCRATCH_DB = "adops360_monthly_reviews_migration_test"
TABLE = "campaign_period_reviews"
COLUMNS = ("id", "campaign_period_id", "kind", "cause", "campaign_line_period_id", "created_by", "created_at")


@pytest.fixture
def scratch(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Config, Engine]]:
    """A database migrated to the revision before the migration, holding one flight and one user."""
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
        _seed_one_flight(connection)
    try:
        yield config, engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def _seed_one_flight(connection: Connection) -> None:
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


def _columns(engine: Engine) -> dict[str, Any]:
    return {column["name"]: column for column in inspect(engine).get_columns(TABLE)}


def _revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


@pytest.fixture
def migrated(scratch: tuple[Config, Engine]) -> Engine:
    config, engine = scratch
    command.upgrade(config, AFTER)
    return engine


def _insert(engine: Engine, kind: str = "reviewed", cause: str = "NULL", flight: str = "NULL", period: int = 1,
            author: int = 1) -> None:
    quoted = cause if cause == "NULL" else f"'{cause}'"
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO campaign_period_reviews (campaign_period_id, kind, cause, campaign_line_period_id, created_by)"
            f" VALUES ({period}, '{kind}', {quoted}, {flight}, {author})"))


# ---------------------------------------------------------------- the table


def test_the_table_does_not_exist_before_and_has_its_columns_after(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    assert TABLE not in inspect(engine).get_table_names()

    command.upgrade(config, AFTER)

    assert tuple(_columns(engine)) == COLUMNS


def test_the_cause_and_the_flight_are_the_only_optional_columns(migrated: Engine) -> None:
    columns = _columns(migrated)

    assert {name for name in COLUMNS if columns[name]["nullable"]} == {"cause", "campaign_line_period_id"}


def test_the_types_follow_the_rest_of_the_model(migrated: Engine) -> None:
    columns = _columns(migrated)

    assert str(columns["id"]["type"]) == "BIGINT"
    assert str(columns["created_at"]["type"]) == "TIMESTAMP"


def test_the_index_serves_the_latest_event_of_a_campaign_month(migrated: Engine) -> None:
    indexes = [index["column_names"] for index in inspect(migrated).get_indexes(TABLE)]

    assert ["campaign_period_id", "id"] in indexes


def test_the_moment_defaults_to_now(migrated: Engine) -> None:
    _insert(migrated)

    with migrated.connect() as connection:
        assert connection.execute(text(f"SELECT created_at IS NOT NULL FROM {TABLE}")).scalar() is True


# ---------------------------------------------------------------- kinds and causes


@pytest.mark.parametrize(
    ("kind", "cause", "flight"),
    [
        ("reviewed", "NULL", "NULL"),
        ("reopened", "withdrawn", "NULL"),
        ("reopened", "adjustment", "1"),
        ("reopened", "carryover", "1"),
        ("reopened", "carryover_billable", "1"),
    ],
)
def test_every_valid_event_is_stored(migrated: Engine, kind: str, cause: str, flight: str) -> None:
    _insert(migrated, kind, cause, flight)


@pytest.mark.parametrize(
    ("kind", "cause", "flight"),
    [
        ("reviewed", "withdrawn", "NULL"),
        ("reviewed", "adjustment", "1"),
        ("reopened", "NULL", "NULL"),
        ("reopened", "NULL", "1"),
        ("other", "NULL", "NULL"),
        ("reopened", "other", "NULL"),
    ],
    ids=["review-with-withdrawal", "review-with-edit", "reopening-without-cause", "reopening-with-flight-only",
         "unknown-kind", "unknown-cause"],
)
def test_a_kind_and_a_cause_that_do_not_go_together_are_refused(migrated: Engine, kind: str, cause: str, flight: str) -> None:
    with pytest.raises(IntegrityError):
        _insert(migrated, kind, cause, flight)


@pytest.mark.parametrize("cause", ["adjustment", "carryover", "carryover_billable"])
def test_an_edit_names_the_flight_it_changed(migrated: Engine, cause: str) -> None:
    with pytest.raises(IntegrityError):
        _insert(migrated, "reopened", cause, "NULL")


def test_a_withdrawal_and_a_review_name_no_flight(migrated: Engine) -> None:
    with pytest.raises(IntegrityError):
        _insert(migrated, "reopened", "withdrawn", "1")
    with pytest.raises(IntegrityError):
        _insert(migrated, "reviewed", "NULL", "1")


def test_the_references_must_exist(migrated: Engine) -> None:
    with pytest.raises(IntegrityError):
        _insert(migrated, period=999)
    with pytest.raises(IntegrityError):
        _insert(migrated, "reopened", "adjustment", "999")
    with pytest.raises(IntegrityError):
        _insert(migrated, author=999)


def test_a_campaign_month_may_hold_many_events(migrated: Engine) -> None:
    _insert(migrated)
    _insert(migrated, "reopened", "withdrawn")
    _insert(migrated)

    with migrated.connect() as connection:
        assert connection.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar() == 3


@pytest.mark.parametrize("statement", ["UPDATE {table} SET created_by = created_by", "DELETE FROM {table}"])
def test_the_table_is_append_only(migrated: Engine, statement: str) -> None:
    _insert(migrated)

    with pytest.raises(DBAPIError, match="append-only"), migrated.begin() as connection:
        connection.execute(text(statement.format(table=TABLE)))


# ---------------------------------------------------------------- downgrade and history


def test_downgrade_drops_the_table_and_keeps_the_flights(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    _insert(engine)

    command.downgrade(config, "-1")

    assert TABLE not in inspect(engine).get_table_names()
    assert _revision(engine) == BEFORE
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM campaign_line_periods")).scalar() == 1


def test_the_migration_hangs_from_the_adjustments_migration_and_the_history_has_one_head(
    scratch: tuple[Config, Engine],
) -> None:
    config, _ = scratch
    script = ScriptDirectory.from_config(config)

    assert script.get_revision(AFTER).down_revision == BEFORE
    assert len(script.get_heads()) == 1
