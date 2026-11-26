"""The migration that adds the carry-over of a flight: the volume it received from the previous flight of its line, why,
who wrote it and when, and whether it is billable (campaign/carryover).

The volume defaults to zero and the flag to false, so every flight that exists keeps behaving as before. The database
refuses a negative volume, a volume with no reason, author or moment, and a billable flag set with no author or moment.
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
from sqlalchemy.exc import IntegrityError

from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL

BEFORE = "3a08cce1c979"  # add the closing headers and the snapshot of every closed flight
AFTER = "c4a1b7e92d10"  # the migration under test; later migrations are not part of these tests
SCRATCH_DB = "adops360_carryover_columns_migration_test"
TABLE = "campaign_line_periods"
COLUMNS = (
    "carryover", "carryover_reason", "carryover_set_by", "carryover_set_at", "carryover_billable",
    "carryover_billable_set_by", "carryover_billable_set_at",
)
REQUIRED = {"carryover", "carryover_billable"}


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
        " start_date, end_date) VALUES ('c', 'c', 1, 1, 1, 1, 1, '2026-10-01', '2026-11-30')"))
    connection.execute(text(
        "INSERT INTO campaign_lines (campaign_id, line_number, start_date, end_date, dsp_id, channel_id, format_id, scope,"
        " market_description, contracted_impressions, sale_cpm) VALUES"
        " (1, 1, '2026-10-01', '2026-11-30', 1, 1, 1, 'national', 'x', 1000000, 5.00)"))
    for month, (start, end) in {10: ("2026-10-01", "2026-10-31"), 11: ("2026-11-01", "2026-11-30")}.items():
        connection.execute(text(
            "INSERT INTO campaign_periods (campaign_id, period_year, period_month, period_start, period_end)"
            f" VALUES (1, 2026, {month}, '{start}', '{end}')"))
        connection.execute(text(
            "INSERT INTO campaign_line_periods (campaign_line_id, campaign_period_id, flight_start, flight_end,"
            f" contracted_impressions) VALUES (1, {month - 9}, '{start}', '{end}', 500000)"))
    connection.execute(text(
        "INSERT INTO users (email, full_name, is_active) VALUES ('migration@example.com', 'Migration', true)"))


def _columns(engine: Engine) -> dict[str, Any]:
    return {column["name"]: column for column in inspect(engine).get_columns(TABLE)}


def _revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _set(engine: Engine, assignments: str, flight_id: int = 2) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"UPDATE {TABLE} SET {assignments} WHERE id = {flight_id}"))


def _refused(engine: Engine, assignments: str) -> None:
    with pytest.raises(IntegrityError):
        _set(engine, assignments)


@pytest.fixture
def migrated(scratch: tuple[Config, Engine]) -> Engine:
    config, engine = scratch
    command.upgrade(config, AFTER)
    return engine


# ---------------------------------------------------------------- the columns


def test_the_seven_columns_are_added_and_nothing_else(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    before = set(_columns(engine))

    command.upgrade(config, AFTER)

    assert set(_columns(engine)) - before == set(COLUMNS)


def test_only_the_volume_and_the_flag_are_required(migrated: Engine) -> None:
    columns = _columns(migrated)

    assert {name for name in COLUMNS if not columns[name]["nullable"]} == REQUIRED


def test_the_types_follow_the_rest_of_the_model(migrated: Engine) -> None:
    columns = _columns(migrated)

    assert str(columns["carryover"]["type"]) == "BIGINT"
    assert str(columns["carryover_billable"]["type"]) == "BOOLEAN"
    assert str(columns["carryover_reason"]["type"]) == "TEXT"
    assert str(columns["carryover_set_at"]["type"]) == "TIMESTAMP"
    assert str(columns["carryover_billable_set_at"]["type"]) == "TIMESTAMP"


def test_existing_flights_have_no_carry_over_and_it_is_not_billable(migrated: Engine) -> None:
    with migrated.connect() as connection:
        rows = connection.execute(text(
            f"SELECT carryover, carryover_billable, carryover_reason, carryover_set_by, carryover_set_at FROM {TABLE}"
        )).all()

    assert rows == [(0, False, None, None, None)] * 2


def test_a_new_flight_has_no_carry_over_and_it_is_not_billable_by_default(migrated: Engine) -> None:
    with migrated.begin() as connection:
        connection.execute(text(
            "INSERT INTO campaign_lines (campaign_id, line_number, start_date, end_date, dsp_id, channel_id, format_id,"
            " scope, market_description, contracted_impressions, sale_cpm) VALUES"
            " (1, 2, '2026-10-01', '2026-10-31', 1, 1, 1, 'national', 'x', 1, 5.00)"))
        connection.execute(text(
            f"INSERT INTO {TABLE} (campaign_line_id, campaign_period_id, flight_start, flight_end, contracted_impressions)"
            " VALUES (2, 1, '2026-10-02', '2026-10-03', 1)"))
        row = connection.execute(text(f"SELECT carryover, carryover_billable FROM {TABLE} ORDER BY id DESC LIMIT 1")).one()

    assert tuple(row) == (0, False)


def test_the_contracted_volume_is_not_touched(migrated: Engine) -> None:
    with migrated.connect() as connection:
        assert connection.execute(text(f"SELECT contracted_impressions FROM {TABLE}")).scalars().all() == [500000, 500000]


def test_no_column_is_floating_point(migrated: Engine) -> None:
    columns = _columns(migrated)

    assert not [name for name in COLUMNS if "FLOAT" in str(columns[name]["type"]).upper() or "REAL" in str(columns[name]["type"]).upper()]


# ---------------------------------------------------------------- what the database refuses


def test_a_carry_over_with_its_reason_author_and_moment_is_stored(migrated: Engine) -> None:
    _set(migrated, "carryover = 100000, carryover_reason = 'Lo no entregado en octubre', carryover_set_by = 1,"
                   " carryover_set_at = '2026-11-02 10:00'")

    with migrated.connect() as connection:
        assert connection.execute(text(f"SELECT carryover FROM {TABLE} WHERE id = 2")).scalar() == 100000


def test_a_negative_carry_over_is_refused(migrated: Engine) -> None:
    _refused(migrated, "carryover = -1, carryover_reason = 'x', carryover_set_by = 1, carryover_set_at = now()")


@pytest.mark.parametrize(
    "assignments",
    [
        "carryover = 1, carryover_set_by = 1, carryover_set_at = now()",
        "carryover = 1, carryover_reason = 'x', carryover_set_at = now()",
        "carryover = 1, carryover_reason = 'x', carryover_set_by = 1",
        "carryover = 1, carryover_reason = '   ', carryover_set_by = 1, carryover_set_at = now()",
    ],
    ids=["no-reason", "no-author", "no-moment", "blank-reason"],
)
def test_a_carry_over_without_its_reason_author_or_moment_is_refused(migrated: Engine, assignments: str) -> None:
    _refused(migrated, assignments)


def test_a_removed_carry_over_may_keep_its_reason_author_and_moment(migrated: Engine) -> None:
    _set(migrated, "carryover = 100, carryover_reason = 'x', carryover_set_by = 1, carryover_set_at = now()")

    _set(migrated, "carryover = 0, carryover_reason = 'Ya no hace falta', carryover_set_by = 1, carryover_set_at = now()")

    with migrated.connect() as connection:
        assert connection.execute(text(f"SELECT carryover FROM {TABLE} WHERE id = 2")).scalar() == 0


def test_a_billable_flag_set_to_true_needs_its_author_and_moment(migrated: Engine) -> None:
    _refused(migrated, "carryover_billable = true")
    _refused(migrated, "carryover_billable = true, carryover_billable_set_by = 1")
    _refused(migrated, "carryover_billable = true, carryover_billable_set_at = now()")

    _set(migrated, "carryover_billable = true, carryover_billable_set_by = 1, carryover_billable_set_at = now()")

    with migrated.connect() as connection:
        assert connection.execute(text(f"SELECT carryover_billable FROM {TABLE} WHERE id = 2")).scalar() is True


def test_the_authors_are_users(migrated: Engine) -> None:
    _refused(migrated, "carryover = 1, carryover_reason = 'x', carryover_set_by = 999, carryover_set_at = now()")
    _refused(migrated, "carryover_billable = true, carryover_billable_set_by = 999, carryover_billable_set_at = now()")


# ---------------------------------------------------------------- downgrade and history


def test_downgrade_drops_the_seven_columns_and_keeps_the_flights(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    command.upgrade(config, AFTER)
    _set(engine, "carryover = 1, carryover_reason = 'x', carryover_set_by = 1, carryover_set_at = now()")

    command.downgrade(config, "-1")

    assert not set(COLUMNS) & set(_columns(engine))
    assert _revision(engine) == BEFORE
    with engine.connect() as connection:
        assert connection.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar() == 2


def test_the_migration_hangs_from_the_closing_snapshot_migration_and_the_history_has_one_head(
    scratch: tuple[Config, Engine],
) -> None:
    config, _ = scratch
    script = ScriptDirectory.from_config(config)

    assert script.get_revision(AFTER).down_revision == BEFORE
    assert len(script.get_heads()) == 1
