"""The margin tables: rebate schedules and brackets, platform rate settings, and the frozen applied rates."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Numeric, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.infrastructure.persistence.models.campaign import CampaignLinePeriodRecord, CampaignLineRecord, CampaignRecord
from app.infrastructure.persistence.models.identity import UserRecord
from app.infrastructure.persistence.models.margin import (
    AppliedRateBracketRecord,
    AppliedRateRecord,
    PlatformRateSettingRecord,
    RebateBracketRecord,
    RebateScheduleRecord,
)
from app.infrastructure.persistence.models.masters import AgencyRecord
from tests.fixtures.delivery_data import insert_campaign_line


class _Ids:
    def __init__(self, session):
        line_id = insert_campaign_line(session)
        line = session.get(CampaignLineRecord, line_id)
        campaign = session.get(CampaignRecord, line.campaign_id)
        agency = session.get(AgencyRecord, campaign.agency_id)
        self.line_id = line_id
        self.channel_id = line.channel_id
        self.campaign_type_id = campaign.campaign_type_id
        self.agency_id = agency.id
        self.group_id = agency.holding_group_id
        self.flight_id = session.scalars(
            select(CampaignLinePeriodRecord.id).where(CampaignLinePeriodRecord.campaign_line_id == line_id)
        ).one()
        user = UserRecord(email="margin-schema@example.com", full_name="Margin Schema", is_active=True)
        session.add(user)
        session.flush()
        self.user_id = user.id


@pytest.fixture
def ids(rolled_back_session) -> _Ids:
    return _Ids(rolled_back_session)


def _schedule(ids: _Ids, valid_from: date, valid_to: date | None, **overrides: object) -> RebateScheduleRecord:
    fields: dict[str, object] = {
        "holding_group_id": ids.group_id, "agency_id": None, "channel_id": None, "scope": None,
        "valid_from": valid_from, "valid_to": valid_to,
    }
    fields.update(overrides)
    return RebateScheduleRecord(**fields)


def _add(session, record) -> None:
    session.add(record)
    session.flush()


# ---------------------------------------------------------------- rebate schedules (1.1, 1.2)

def test_agency_channel_and_scope_are_optional_and_the_validity_start_is_required():
    columns = {c.name: c for c in RebateScheduleRecord.__table__.columns}

    assert columns["agency_id"].nullable and columns["channel_id"].nullable and columns["scope"].nullable
    assert columns["valid_to"].nullable
    assert not columns["valid_from"].nullable
    assert not columns["holding_group_id"].nullable


def test_a_schedule_whose_validity_overlaps_another_of_the_same_key_is_refused(rolled_back_session, ids):
    _add(rolled_back_session, _schedule(ids, date(2026, 1, 1), date(2026, 6, 30)))

    with pytest.raises(IntegrityError):
        _add(rolled_back_session, _schedule(ids, date(2026, 6, 1), date(2026, 12, 31)))


def test_valid_to_is_inclusive(rolled_back_session, ids):
    _add(rolled_back_session, _schedule(ids, date(2026, 1, 1), date(2026, 4, 30)))

    with pytest.raises(IntegrityError):
        _add(rolled_back_session, _schedule(ids, date(2026, 4, 30), date(2026, 12, 31)))


def test_back_to_back_validity_is_accepted(rolled_back_session, ids):
    _add(rolled_back_session, _schedule(ids, date(2026, 1, 1), date(2026, 4, 30)))

    _add(rolled_back_session, _schedule(ids, date(2026, 5, 1), date(2026, 12, 31)))


def test_an_open_ended_schedule_overlaps_a_later_one(rolled_back_session, ids):
    _add(rolled_back_session, _schedule(ids, date(2026, 1, 1), None))

    with pytest.raises(IntegrityError):
        _add(rolled_back_session, _schedule(ids, date(2030, 1, 1), date(2030, 12, 31)))


def test_an_open_ended_schedule_does_not_break_the_exclusion_for_an_earlier_one(rolled_back_session, ids):
    _add(rolled_back_session, _schedule(ids, date(2026, 6, 1), None))

    _add(rolled_back_session, _schedule(ids, date(2025, 1, 1), date(2026, 5, 31)))


def test_two_group_wide_schedules_conflict_even_though_their_optional_keys_are_null(rolled_back_session, ids):
    _add(rolled_back_session, _schedule(ids, date(2026, 1, 1), date(2026, 12, 31)))

    with pytest.raises(IntegrityError):
        _add(rolled_back_session, _schedule(ids, date(2026, 3, 1), date(2026, 3, 31)))


@pytest.mark.parametrize("difference", ["channel", "scope", "agency"])
def test_schedules_of_different_keys_may_overlap(rolled_back_session, ids, difference: str):
    _add(rolled_back_session, _schedule(ids, date(2026, 1, 1), date(2026, 12, 31)))
    override = {
        "channel": {"channel_id": ids.channel_id},
        "scope": {"scope": "national"},
        "agency": {"agency_id": ids.agency_id},
    }[difference]

    _add(rolled_back_session, _schedule(ids, date(2026, 1, 1), date(2026, 12, 31), **override))


def test_a_schedule_cannot_end_before_it_starts(rolled_back_session, ids):
    with pytest.raises(IntegrityError):
        _add(rolled_back_session, _schedule(ids, date(2026, 6, 1), date(2026, 5, 1)))


def test_brackets_are_exact_numerics_and_round_trip_without_loss(rolled_back_session, ids):
    schedule = _schedule(ids, date(2026, 1, 1), None)
    _add(rolled_back_session, schedule)
    bracket = RebateBracketRecord(
        rebate_schedule_id=schedule.id, position=1, lower=Decimal("0"), upper=None, rate=Decimal("0.123456789012")
    )
    _add(rolled_back_session, bracket)
    rolled_back_session.expire_all()

    stored = rolled_back_session.get(RebateBracketRecord, bracket.id)

    assert stored.rate == Decimal("0.123456789012")
    for name in ("lower", "upper", "rate"):
        assert isinstance(RebateBracketRecord.__table__.c[name].type, Numeric)


def test_a_schedule_has_one_bracket_per_position(rolled_back_session, ids):
    schedule = _schedule(ids, date(2026, 1, 1), None)
    _add(rolled_back_session, schedule)
    _add(rolled_back_session, RebateBracketRecord(
        rebate_schedule_id=schedule.id, position=1, lower=Decimal(0), upper=Decimal(100), rate=Decimal("0.1")))

    with pytest.raises(IntegrityError):
        _add(rolled_back_session, RebateBracketRecord(
            rebate_schedule_id=schedule.id, position=1, lower=Decimal(100), upper=None, rate=Decimal("0.2")))


def test_a_bracket_cannot_have_an_upper_threshold_not_above_its_lower(rolled_back_session, ids):
    schedule = _schedule(ids, date(2026, 1, 1), None)
    _add(rolled_back_session, schedule)

    with pytest.raises(IntegrityError):
        _add(rolled_back_session, RebateBracketRecord(
            rebate_schedule_id=schedule.id, position=1, lower=Decimal(100), upper=Decimal(100), rate=Decimal("0.1")))


# ---------------------------------------------------------------- platform rate settings (1.4)

def _setting(level: str, ids: _Ids, **overrides: object) -> PlatformRateSettingRecord:
    fields: dict[str, object] = {
        "level": level, "campaign_line_id": None, "agency_id": None, "campaign_type_id": None,
        "rate_per_thousand": Decimal("1.25"), "created_by": ids.user_id,
    }
    fields.update(overrides)
    return PlatformRateSettingRecord(**fields)


def test_the_migration_inserts_the_system_rate_as_data(rolled_back_session):
    system = rolled_back_session.scalars(
        select(PlatformRateSettingRecord).where(PlatformRateSettingRecord.level == "system")
    ).all()

    assert [row.rate_per_thousand for row in system] == [Decimal("1.00")]
    assert system[0].created_by is None


@pytest.mark.parametrize(
    ("level", "key"),
    [("line", "campaign_line_id"), ("agency", "agency_id"), ("campaign_type", "campaign_type_id")],
)
def test_a_level_needs_its_scope_key(rolled_back_session, ids, level: str, key: str):
    other = {"line": ids.line_id, "agency": ids.agency_id, "campaign_type": ids.campaign_type_id}[level]
    _add(rolled_back_session, _setting(level, ids, **{key: other}))  # accepted with its key

    with pytest.raises(IntegrityError):
        _add(rolled_back_session, _setting(level, ids))  # absent key


def test_a_level_cannot_carry_another_levels_key(rolled_back_session, ids):
    with pytest.raises(IntegrityError):
        _add(rolled_back_session, _setting("agency", ids, agency_id=ids.agency_id, campaign_line_id=ids.line_id))


def test_the_system_level_carries_no_key(rolled_back_session, ids):
    with pytest.raises(IntegrityError):
        _add(rolled_back_session, _setting("system", ids, agency_id=ids.agency_id))


def test_only_the_system_level_may_have_no_author(rolled_back_session, ids):
    _add(rolled_back_session, _setting("system", ids, created_by=None))

    with pytest.raises(IntegrityError):
        _add(rolled_back_session, _setting("agency", ids, agency_id=ids.agency_id, created_by=None))


def test_a_rate_is_never_negative_and_an_unknown_level_is_refused(rolled_back_session, ids):
    with pytest.raises(IntegrityError):
        _add(rolled_back_session, _setting("system", ids, rate_per_thousand=Decimal("-1")))
    rolled_back_session.rollback()
    with pytest.raises(IntegrityError):
        _add(rolled_back_session, _setting("galaxy", ids))


def test_settings_are_added_not_replaced_and_every_one_is_stamped(rolled_back_session, ids):
    _add(rolled_back_session, _setting("agency", ids, agency_id=ids.agency_id, rate_per_thousand=Decimal("1.10")))
    _add(rolled_back_session, _setting("agency", ids, agency_id=ids.agency_id, rate_per_thousand=Decimal("1.30")))

    rows = rolled_back_session.scalars(
        select(PlatformRateSettingRecord).where(PlatformRateSettingRecord.level == "agency")
    ).all()

    assert len(rows) == 2
    assert all(isinstance(row.created_at, datetime) for row in rows)


# ---------------------------------------------------------------- applied rates (1.5)

def _applied(ids: _Ids, **overrides: object) -> AppliedRateRecord:
    fields: dict[str, object] = {
        "campaign_line_period_id": ids.flight_id,
        "rebate_schedule_id": None,
        "ladder_step": 8,
        "source_year": None,
        "agency_exception": False,
        "zero_reason": "no_schedule",
        "effective_rate": Decimal("0"),
        "counter_group_id": ids.group_id,
        "counter_agency_id": None,
        "counter_channel_id": ids.channel_id,
        "counter_year": 2026,
        "position_before": Decimal("0"),
        "position_after": Decimal("3631.01"),
        "rebate_amount": Decimal("0"),
        "platform_rate": Decimal("1.00"),
        "closed_at": datetime(2026, 9, 1, 12, 0),
        "closed_by": ids.user_id,
    }
    fields.update(overrides)
    return AppliedRateRecord(**fields)


def test_a_flight_has_one_applied_rate_row(rolled_back_session, ids):
    _add(rolled_back_session, _applied(ids))

    with pytest.raises(IntegrityError):
        _add(rolled_back_session, _applied(ids))


def test_applied_amounts_round_trip_without_losing_precision(rolled_back_session, ids):
    exact = Decimal("907.752500000001")
    row = _applied(ids, rebate_amount=exact, effective_rate=Decimal("0.183333333333"), position_before=Decimal("90000.125"))
    _add(rolled_back_session, row)
    _add(rolled_back_session, AppliedRateBracketRecord(
        applied_rate_id=row.id, position=1, lower=Decimal("0"), upper=Decimal("100000"),
        rate=Decimal("0.150000000000"), amount=Decimal("10000.5"), rebate=Decimal("1500.075")))
    rolled_back_session.expire_all()

    stored = rolled_back_session.get(AppliedRateRecord, row.id)
    bracket = rolled_back_session.scalars(select(AppliedRateBracketRecord)).one()

    assert stored.rebate_amount == exact
    assert stored.effective_rate == Decimal("0.183333333333")
    assert stored.position_before == Decimal("90000.125")
    assert (bracket.amount, bracket.rebate) == (Decimal("10000.5"), Decimal("1500.075"))
    for column in AppliedRateRecord.__table__.columns:
        assert not (column.type.__class__.__name__ in {"Float", "REAL", "DOUBLE_PRECISION"})


def test_an_applied_rate_row_cannot_be_updated(rolled_back_session, ids):
    row = _applied(ids)
    _add(rolled_back_session, row)

    with pytest.raises(DBAPIError):
        rolled_back_session.execute(text("UPDATE applied_rates SET rebate_amount = 1 WHERE id = :id"), {"id": row.id})


def test_an_applied_rate_row_cannot_be_deleted(rolled_back_session, ids):
    row = _applied(ids)
    _add(rolled_back_session, row)

    with pytest.raises(DBAPIError):
        rolled_back_session.execute(text("DELETE FROM applied_rates WHERE id = :id"), {"id": row.id})


def test_a_breakdown_row_cannot_be_updated(rolled_back_session, ids):
    row = _applied(ids)
    _add(rolled_back_session, row)
    bracket = AppliedRateBracketRecord(
        applied_rate_id=row.id, position=1, lower=Decimal(0), upper=None, rate=Decimal("0.1"),
        amount=Decimal(10), rebate=Decimal(1))
    _add(rolled_back_session, bracket)

    with pytest.raises(DBAPIError):
        rolled_back_session.execute(text("UPDATE applied_rate_brackets SET rebate = 2 WHERE id = :id"), {"id": bracket.id})


def test_the_ladder_step_and_zero_reason_are_constrained(rolled_back_session, ids):
    with pytest.raises(IntegrityError):
        _add(rolled_back_session, _applied(ids, ladder_step=7))
    rolled_back_session.rollback()
    with pytest.raises(IntegrityError):
        _add(rolled_back_session, _applied(ids, zero_reason="because"))


def test_the_columns_of_the_margin_tables_hold_no_floating_point(rolled_back_session):
    inspector = inspect(rolled_back_session.get_bind())
    for table in ("rebate_schedules", "rebate_brackets", "platform_rate_settings", "applied_rates", "applied_rate_brackets"):
        for column in inspector.get_columns(table):
            assert column["type"].__class__.__name__ not in {"FLOAT", "REAL", "DOUBLE_PRECISION"}, (table, column["name"])
