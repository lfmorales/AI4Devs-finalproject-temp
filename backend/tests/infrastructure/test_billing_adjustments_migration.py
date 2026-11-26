"""The migration that adds the billing adjustments of a committed flight (finance/billing-adjustment).

The table is append-only: an adjustment is never updated or deleted, the latest of a flight is the one in force. The
database refuses an unknown basis, an amount with a basis other than `custom`, a `custom` basis without its amount, a
negative amount, an amount with more than two decimals and a blank reason.
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

BEFORE = "c4a1b7e92d10"  # add the carry-over of a flight
AFTER = "d7e2a9f41b36"  # the migration under test; later migrations are not part of these tests
SCRATCH_DB = "adops360_billing_adjustments_migration_test"
TABLE = "flight_billing_adjustments"
COLUMNS = ("id", "campaign_line_period_id", "basis", "amount", "reason", "created_by", "created_at")
INSERT = (
    "INSERT INTO flight_billing_adjustments (campaign_line_period_id, basis, amount, reason, created_by)"
    " VALUES ({flight}, '{basis}', {amount}, '{reason}', {author})"
)


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


def _insert(engine: Engine, basis: str = "contracted", amount: str = "NULL", reason: str = "Acuerdo", flight: int = 1,
            author: int = 1) -> None:
    with engine.begin() as connection:
        connection.execute(text(INSERT.format(flight=flight, basis=basis, amount=amount, reason=reason, author=author)))


# ---------------------------------------------------------------- the table


def test_the_table_does_not_exist_before_and_has_its_columns_after(scratch: tuple[Config, Engine]) -> None:
    config, engine = scratch
    assert TABLE not in inspect(engine).get_table_names()

    command.upgrade(config, AFTER)

    assert tuple(_columns(engine)) == COLUMNS


def test_only_the_amount_is_optional(migrated: Engine) -> None:
    columns = _columns(migrated)

    assert {name for name in COLUMNS if columns[name]["nullable"]} == {"amount"}


def test_the_types_follow_the_rest_of_the_model(migrated: Engine) -> None:
    columns = _columns(migrated)

    assert str(columns["id"]["type"]) == "BIGINT"
    assert str(columns["amount"]["type"]) == "NUMERIC(18, 2)"
    assert str(columns["reason"]["type"]) == "TEXT"
    assert str(columns["created_at"]["type"]) == "TIMESTAMP"
    assert not [name for name in COLUMNS if "FLOAT" in str(columns[name]["type"]).upper()]


def test_the_creation_moment_defaults_to_now(migrated: Engine) -> None:
    _insert(migrated)

    with migrated.connect() as connection:
        assert connection.execute(text(f"SELECT created_at IS NOT NULL FROM {TABLE}")).scalar() is True


def test_the_index_serves_the_adjustment_in_force_of_a_flight(migrated: Engine) -> None:
    indexes = {index["name"]: index["column_names"] for index in inspect(migrated).get_indexes(TABLE)}

    assert ["campaign_line_period_id", "id"] in indexes.values()


# ---------------------------------------------------------------- what the database refuses


@pytest.mark.parametrize(
    ("basis", "amount"),
    [("minimum", "NULL"), ("delivered", "NULL"), ("contracted", "NULL"), ("custom", "4200.00"), ("custom", "0.00")],
)
def test_every_basis_is_stored_with_its_amount_rule(migrated: Engine, basis: str, amount: str) -> None:
    _insert(migrated, basis=basis, amount=amount)


@pytest.mark.parametrize("basis", ["reported", "other", ""])
def test_an_unknown_basis_is_refused(migrated: Engine, basis: str) -> None:
    with pytest.raises(IntegrityError):
        _insert(migrated, basis=basis)


@pytest.mark.parametrize("basis", ["minimum", "delivered", "contracted"])
def test_an_amount_with_another_basis_than_custom_is_refused(migrated: Engine, basis: str) -> None:
    with pytest.raises(IntegrityError):
        _insert(migrated, basis=basis, amount="100.00")


def test_the_custom_basis_needs_its_amount(migrated: Engine) -> None:
    with pytest.raises(IntegrityError):
        _insert(migrated, basis="custom")


def test_a_negative_amount_is_refused(migrated: Engine) -> None:
    with pytest.raises(IntegrityError):
        _insert(migrated, basis="custom", amount="-0.01")


@pytest.mark.parametrize("reason", ["", "   "], ids=["empty", "spaces"])
def test_a_blank_reason_is_refused(migrated: Engine, reason: str) -> None:
    with pytest.raises(IntegrityError):
        _insert(migrated, reason=reason)


def test_the_flight_and_the_author_must_exist(migrated: Engine) -> None:
    with pytest.raises(IntegrityError):
        _insert(migrated, flight=999)
    with pytest.raises(IntegrityError):
        _insert(migrated, author=999)


def test_a_flight_may_have_many_adjustments(migrated: Engine) -> None:
    _insert(migrated, basis="contracted")
    _insert(migrated, basis="custom", amount="4200.00")

    with migrated.connect() as connection:
        assert connection.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar() == 2


@pytest.mark.parametrize("statement", ["UPDATE {table} SET reason = 'x'", "DELETE FROM {table}"])
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


def test_the_migration_hangs_from_the_carry_over_migration_and_the_history_has_one_head(
    scratch: tuple[Config, Engine],
) -> None:
    config, _ = scratch
    script = ScriptDirectory.from_config(config)

    assert script.get_revision(AFTER).down_revision == BEFORE
    assert len(script.get_heads()) == 1
