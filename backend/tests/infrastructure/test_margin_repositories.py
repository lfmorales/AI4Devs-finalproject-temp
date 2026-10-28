"""The SQLAlchemy repositories behind the margin: schedules, platform rates, flights with delivery, frozen rates."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.domain.services.platform_rate import resolve_platform_rate
from app.domain.services.priced_flights import price_flights
from app.domain.value_objects.priced_flight import PlatformRates
from app.domain.value_objects.rebate import Bracket, CounterKey
from app.infrastructure.persistence.models.campaign import CampaignLineRecord, CampaignRecord
from app.infrastructure.persistence.models.margin import (
    AppliedRateBracketRecord,
    AppliedRateRecord,
    PlatformRateSettingRecord,
    RebateBracketRecord,
    RebateScheduleRecord,
)
from app.infrastructure.persistence.models.masters import AgencyRecord, ChannelRecord
from app.infrastructure.persistence.repositories.sqlalchemy_margin_repositories import (
    SqlAlchemyAppliedRateRepository,
    SqlAlchemyMarginFlightRepository,
    SqlAlchemyPlatformRateRepository,
    SqlAlchemyRebateScheduleRepository,
)
from tests.fixtures.delivery_data import (
    add_line_to_campaign,
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    insert_user,
    replace_flights,
)

AS_OF = date(2026, 9, 5)


def _line(session, **kwargs) -> int:
    return insert_campaign_line(session, **kwargs)


def _group_and_agency(session, line_id: int) -> tuple[int, int]:
    line = session.get(CampaignLineRecord, line_id)
    campaign = session.get(CampaignRecord, line.campaign_id)
    agency = session.get(AgencyRecord, campaign.agency_id)
    return agency.holding_group_id, agency.id


# ---------------------------------------------------------------- rebate schedules

def test_schedules_come_back_with_their_brackets_and_the_channel_by_name(rolled_back_session):
    line_id = _line(rolled_back_session)
    group_id, agency_id = _group_and_agency(rolled_back_session, line_id)
    channel = rolled_back_session.get(ChannelRecord, rolled_back_session.get(CampaignLineRecord, line_id).channel_id)
    schedule = RebateScheduleRecord(
        holding_group_id=group_id, agency_id=agency_id, channel_id=channel.id, scope="national",
        valid_from=date(2026, 1, 1), valid_to=None,
    )
    rolled_back_session.add(schedule)
    rolled_back_session.flush()
    rolled_back_session.add_all([
        RebateBracketRecord(rebate_schedule_id=schedule.id, position=2, lower=Decimal(100_000), upper=None, rate=Decimal("0.20")),
        RebateBracketRecord(rebate_schedule_id=schedule.id, position=1, lower=Decimal(0), upper=Decimal(100_000), rate=Decimal("0.15")),
    ])
    rolled_back_session.flush()

    (loaded,) = SqlAlchemyRebateScheduleRepository(rolled_back_session).list_schedules()

    assert (loaded.group_id, loaded.agency_id, loaded.channel, loaded.scope) == (group_id, agency_id, channel.name, "national")
    assert (loaded.valid_from, loaded.valid_to) == (date(2026, 1, 1), None)
    assert loaded.brackets == (
        Bracket(Decimal(0), Decimal(100_000), Decimal("0.15")),
        Bracket(Decimal(100_000), None, Decimal("0.20")),
    )


def test_a_schedule_without_channel_or_scope_loads_with_none(rolled_back_session):
    line_id = _line(rolled_back_session)
    group_id, _ = _group_and_agency(rolled_back_session, line_id)
    schedule = RebateScheduleRecord(holding_group_id=group_id, valid_from=date(2026, 1, 1))
    rolled_back_session.add(schedule)
    rolled_back_session.flush()
    rolled_back_session.add(RebateBracketRecord(
        rebate_schedule_id=schedule.id, position=1, lower=Decimal(0), upper=None, rate=Decimal("0.25")))
    rolled_back_session.flush()

    (loaded,) = SqlAlchemyRebateScheduleRepository(rolled_back_session).list_schedules()

    assert (loaded.agency_id, loaded.channel, loaded.scope) == (None, None, None)


# ---------------------------------------------------------------- platform rates

def _setting(session, level: str, rate: str, user_id: int, **keys: int) -> None:
    session.add(PlatformRateSettingRecord(
        level=level, rate_per_thousand=Decimal(rate), created_by=user_id,
        campaign_line_id=keys.get("line"), agency_id=keys.get("agency"), campaign_type_id=keys.get("campaign_type"),
    ))
    session.flush()


def test_the_system_rate_is_the_one_the_migration_inserted(rolled_back_session):
    assert SqlAlchemyPlatformRateRepository(rolled_back_session).current_rates() == PlatformRates(system=Decimal("1.000000"))


def test_a_new_system_row_changes_the_resolved_rate_without_touching_code(rolled_back_session):
    user_id = insert_user(rolled_back_session)
    repository = SqlAlchemyPlatformRateRepository(rolled_back_session)
    before = resolve_platform_rate(system=repository.current_rates().system)

    _setting(rolled_back_session, "system", "1.250000", user_id)
    after = resolve_platform_rate(system=repository.current_rates().system)

    assert (before.rate, after.rate) == (Decimal("1.000000"), Decimal("1.250000"))


def test_for_each_level_and_key_the_latest_setting_wins(rolled_back_session):
    line_id = _line(rolled_back_session)
    _, agency_id = _group_and_agency(rolled_back_session, line_id)
    user_id = insert_user(rolled_back_session)
    _setting(rolled_back_session, "agency", "1.10", user_id, agency=agency_id)
    _setting(rolled_back_session, "agency", "1.30", user_id, agency=agency_id)
    _setting(rolled_back_session, "line", "0.90", user_id, line=line_id)

    rates = SqlAlchemyPlatformRateRepository(rolled_back_session).current_rates()

    assert rates.by_agency == {agency_id: Decimal("1.30")}
    assert rates.by_line == {line_id: Decimal("0.90")}
    assert rates.by_campaign_type == {}


# ---------------------------------------------------------------- flights with delivery

def test_open_ended_flights_carry_the_delivery_of_their_own_window_only(rolled_back_session):
    line_id = _line(rolled_back_session, start_date=date(2026, 8, 1), end_date=date(2026, 9, 30))
    replace_flights(rolled_back_session, line_id, [(date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), date(2026, 9, 30))])
    batch = insert_ingestion_batch(rolled_back_session)
    insert_delivery(rolled_back_session, line_id, date(2026, 8, 10), 1000, batch, Decimal("1.50"))
    insert_delivery(rolled_back_session, line_id, date(2026, 8, 31), 500, batch, Decimal("0.25"))
    insert_delivery(rolled_back_session, line_id, date(2026, 9, 1), 9999, batch, Decimal("9.99"))

    (august,) = SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)

    assert (august.delivered_impressions, august.media_cost) == (1500, Decimal("1.75"))
    assert (august.flight_start, august.flight_end) == (date(2026, 8, 1), date(2026, 8, 31))
    assert august.sale_cpm == Decimal("5.00")
    assert august.contracted_impressions == 1_000_000


def test_a_flight_without_delivery_has_zero_delivered_and_a_decimal_zero_cost(rolled_back_session):
    _line(rolled_back_session)

    (flight,) = SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)

    assert flight.delivered_impressions == 0
    assert flight.media_cost == Decimal("0") and isinstance(flight.media_cost, Decimal)


def test_a_flight_that_has_not_ended_is_not_open_for_closing(rolled_back_session):
    _line(rolled_back_session)

    assert SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, date(2026, 8, 30)) == []
    assert len(SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, date(2026, 8, 31))) == 1


def test_only_the_requested_month_is_returned(rolled_back_session):
    _line(rolled_back_session)

    assert SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 7, AS_OF) == []


def test_inactive_campaigns_are_included(rolled_back_session):
    _line(rolled_back_session, status="inactive")

    assert len(SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)) == 1


def test_flights_come_back_by_start_then_id(rolled_back_session):
    first = _line(rolled_back_session)
    second = add_line_to_campaign(rolled_back_session, first, line_number=2)
    third = add_line_to_campaign(rolled_back_session, first, line_number=3)

    flights = SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)

    assert [f.campaign_line_id for f in flights] == [first, second, third]
    assert [f.flight_id for f in flights] == sorted(f.flight_id for f in flights)


def test_a_frozen_flight_is_no_longer_open(rolled_back_session):
    line_id = _line(rolled_back_session)
    user_id = insert_user(rolled_back_session)
    flights = SqlAlchemyMarginFlightRepository(rolled_back_session)
    (facts,) = flights.open_ended_flights(2026, 8, AS_OF)
    priced = price_flights([], PlatformRates(system=Decimal("1.00")), [facts], AS_OF)
    SqlAlchemyAppliedRateRepository(rolled_back_session).save(priced, datetime(2026, 9, 5, 9, 0), user_id)

    assert flights.open_ended_flights(2026, 8, AS_OF) == []
    assert SqlAlchemyAppliedRateRepository(rolled_back_session).count_frozen(2026, 8) == 1
    assert line_id == facts.campaign_line_id


def test_the_earliest_earlier_month_with_open_flights(rolled_back_session):
    line_id = _line(rolled_back_session, start_date=date(2026, 6, 1), end_date=date(2026, 8, 31))
    replace_flights(rolled_back_session, line_id, [
        (date(2026, 6, 1), date(2026, 6, 30)), (date(2026, 7, 1), date(2026, 7, 31)), (date(2026, 8, 1), date(2026, 8, 31)),
    ])
    flights = SqlAlchemyMarginFlightRepository(rolled_back_session)

    assert flights.earliest_month_with_open_flights(2026, 8, AS_OF) == 6
    assert flights.earliest_month_with_open_flights(2026, 6, AS_OF) is None
    assert flights.earliest_month_with_open_flights(2025, 12, AS_OF) is None


def test_a_month_that_has_not_ended_does_not_block(rolled_back_session):
    line_id = _line(rolled_back_session, start_date=date(2026, 8, 1), end_date=date(2026, 9, 30))
    replace_flights(rolled_back_session, line_id, [(date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), date(2026, 9, 30))])

    assert SqlAlchemyMarginFlightRepository(rolled_back_session).earliest_month_with_open_flights(2026, 10, AS_OF) == 8


# ---------------------------------------------------------------- applied rates

def _freeze(session, month_flights, schedules, user_id, as_of=AS_OF, opening=None):
    priced = price_flights(schedules, PlatformRates(system=Decimal("1.00")), month_flights, as_of, opening)
    SqlAlchemyAppliedRateRepository(session).save(priced, datetime(2026, 9, 5, 9, 0), user_id)
    return priced


def test_saved_rates_keep_every_decision_and_the_breakdown(rolled_back_session):
    line_id = _line(rolled_back_session)
    group_id, agency_id = _group_and_agency(rolled_back_session, line_id)
    user_id = insert_user(rolled_back_session)
    schedule = RebateScheduleRecord(holding_group_id=group_id, valid_from=date(2026, 1, 1))
    rolled_back_session.add(schedule)
    rolled_back_session.flush()
    rolled_back_session.add_all([
        RebateBracketRecord(rebate_schedule_id=schedule.id, position=1, lower=Decimal(0), upper=Decimal(1000), rate=Decimal("0.15")),
        RebateBracketRecord(rebate_schedule_id=schedule.id, position=2, lower=Decimal(1000), upper=None, rate=Decimal("0.20")),
    ])
    rolled_back_session.flush()
    schedules = SqlAlchemyRebateScheduleRepository(rolled_back_session).list_schedules()
    (facts,) = SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)

    (priced,) = _freeze(rolled_back_session, [facts], schedules, user_id)
    rolled_back_session.expire_all()
    row = rolled_back_session.scalars(select(AppliedRateRecord)).one()
    breakdown = rolled_back_session.scalars(select(AppliedRateBracketRecord).order_by(AppliedRateBracketRecord.position)).all()

    assert row.campaign_line_period_id == facts.flight_id
    assert (row.rebate_schedule_id, row.ladder_step, row.agency_exception, row.zero_reason) == (schedule.id, 6, False, None)
    assert row.source_year == 2026
    assert row.rebate_amount == priced.rebate.rebate
    assert row.effective_rate == priced.rebate.effective_rate.quantize(Decimal("0.000000000001"))
    assert (row.position_before, row.position_after) == (Decimal(0), Decimal("5000.00"))
    assert row.platform_rate == Decimal("1.00")
    assert (row.counter_group_id, row.counter_agency_id, row.counter_year) == (group_id, None, 2026)
    assert (row.closed_at, row.closed_by) == (datetime(2026, 9, 5, 9, 0), user_id)
    assert [(b.position, b.lower, b.upper, b.rate, b.amount, b.rebate) for b in breakdown] == [
        (1, Decimal(0), Decimal(1000), Decimal("0.15"), Decimal(1000), Decimal(150)),
        (2, Decimal(1000), None, Decimal("0.20"), Decimal(4000), Decimal(800)),
    ]
    assert agency_id is not None


def test_a_flight_without_a_schedule_is_saved_as_an_explicit_zero_with_its_reason(rolled_back_session):
    _line(rolled_back_session)
    user_id = insert_user(rolled_back_session)
    (facts,) = SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)

    _freeze(rolled_back_session, [facts], [], user_id)
    row = rolled_back_session.scalars(select(AppliedRateRecord)).one()

    assert (row.ladder_step, row.zero_reason, row.rebate_schedule_id, row.rebate_amount) == (
        8, "no_schedule_for_year", None, Decimal(0))
    assert rolled_back_session.scalar(select(func.count()).select_from(AppliedRateBracketRecord)) == 0


def test_opening_positions_are_the_position_after_the_latest_frozen_flight_of_each_counter(rolled_back_session):
    line_id = _line(rolled_back_session, start_date=date(2026, 6, 1), end_date=date(2026, 8, 31))
    replace_flights(rolled_back_session, line_id, [
        (date(2026, 6, 1), date(2026, 6, 30)), (date(2026, 7, 1), date(2026, 7, 31)), (date(2026, 8, 1), date(2026, 8, 31)),
    ])
    group_id, _ = _group_and_agency(rolled_back_session, line_id)
    user_id = insert_user(rolled_back_session)
    schedule = RebateScheduleRecord(holding_group_id=group_id, valid_from=date(2026, 1, 1))
    rolled_back_session.add(schedule)
    rolled_back_session.flush()
    rolled_back_session.add(RebateBracketRecord(
        rebate_schedule_id=schedule.id, position=1, lower=Decimal(0), upper=None, rate=Decimal("0.25")))
    rolled_back_session.flush()
    schedules = SqlAlchemyRebateScheduleRepository(rolled_back_session).list_schedules()
    flights = SqlAlchemyMarginFlightRepository(rolled_back_session)
    _freeze(rolled_back_session, flights.open_ended_flights(2026, 6, AS_OF), schedules, user_id)
    applied = SqlAlchemyAppliedRateRepository(rolled_back_session)
    _freeze(rolled_back_session, flights.open_ended_flights(2026, 7, AS_OF), schedules, user_id, opening=applied.opening_positions(2026))

    positions = applied.opening_positions(2026)

    channel_name = rolled_back_session.scalars(select(ChannelRecord.name)).first()
    # Two frozen flights of 1,000,000 impressions at 5.00 EUR per thousand: 5,000 EUR each.
    assert positions == {CounterKey(group_id, None, channel_name, 2026): Decimal("10000.00")}
    assert SqlAlchemyAppliedRateRepository(rolled_back_session).opening_positions(2025) == {}


def test_the_opening_position_feeds_the_next_closing(rolled_back_session):
    line_id = _line(rolled_back_session, start_date=date(2026, 7, 1), end_date=date(2026, 8, 31))
    replace_flights(rolled_back_session, line_id, [(date(2026, 7, 1), date(2026, 7, 31)), (date(2026, 8, 1), date(2026, 8, 31))])
    group_id, _ = _group_and_agency(rolled_back_session, line_id)
    user_id = insert_user(rolled_back_session)
    schedule = RebateScheduleRecord(holding_group_id=group_id, valid_from=date(2026, 1, 1))
    rolled_back_session.add(schedule)
    rolled_back_session.flush()
    rolled_back_session.add_all([
        RebateBracketRecord(rebate_schedule_id=schedule.id, position=1, lower=Decimal(0), upper=Decimal(6000), rate=Decimal("0.10")),
        RebateBracketRecord(rebate_schedule_id=schedule.id, position=2, lower=Decimal(6000), upper=None, rate=Decimal("0.30")),
    ])
    rolled_back_session.flush()
    schedules = SqlAlchemyRebateScheduleRepository(rolled_back_session).list_schedules()
    flights = SqlAlchemyMarginFlightRepository(rolled_back_session)
    applied = SqlAlchemyAppliedRateRepository(rolled_back_session)
    _freeze(rolled_back_session, flights.open_ended_flights(2026, 7, AS_OF), schedules, user_id)

    (august,) = _freeze(
        rolled_back_session, flights.open_ended_flights(2026, 8, AS_OF), schedules, user_id,
        opening=applied.opening_positions(2026),
    )

    assert august.rebate.position_before == Decimal("5000.00")
    assert august.rebate.rebate == Decimal("1000.00") * Decimal("0.10") + Decimal("4000.00") * Decimal("0.30")
