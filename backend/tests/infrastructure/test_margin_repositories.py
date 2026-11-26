"""The SQLAlchemy repositories behind the margin: schedules, platform rates, flights with delivery, frozen rates."""

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.domain.services.closed_flight import snapshot_of
from app.domain.services.platform_rate import resolve_platform_rate
from app.domain.services.priced_flights import price_flights
from app.domain.value_objects.billing import BillingAdjustment, BillingBasis
from app.domain.value_objects.priced_flight import FlightFacts, PlatformRates, PricedFlight, ReadFlight
from app.domain.value_objects.rebate import Bracket, CounterKey, RebateSchedule
from app.domain.value_objects.volume_commitment import VolumeCommitment
from app.infrastructure.persistence.models.campaign import CampaignLinePeriodRecord, CampaignLineRecord, CampaignRecord
from app.infrastructure.persistence.models.delivery import IngestionBatchRecord
from app.infrastructure.persistence.models.margin import (
    AppliedRateBracketRecord,
    AppliedRateRecord,
    ClosedFlightSnapshotRecord,
    FlightBillingAdjustmentRecord,
    MonthClosingBatchRecord,
    MonthClosingRecord,
    PlatformRateSettingRecord,
    RebateBracketRecord,
    RebateScheduleRecord,
)
from app.infrastructure.persistence.models.masters import AgencyRecord, ChannelRecord
from app.infrastructure.persistence.repositories.sqlalchemy_margin_repositories import (
    SqlAlchemyAppliedRateRepository,
    SqlAlchemyMarginFlightRepository,
    SqlAlchemyMarginReadRepository,
    SqlAlchemyMonthClosingRepository,
    SqlAlchemyPlatformRateRepository,
    SqlAlchemyRebateScheduleRepository,
)
from tests.fixtures.delivery_data import (
    add_line_to_campaign,
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    insert_other_dsp,
    insert_user,
    replace_flights,
    seeded_dsp_id,
)

AS_OF = date(2026, 9, 5)


def _line(session, **kwargs) -> int:
    return insert_campaign_line(session, **kwargs)


def _deliver_the_contract(session: Session, line_id: int, *days: date) -> None:
    """Each flight, one per day given, delivers its 1,000,000 contracted impressions, so it bills its contracted sale
    (committed-billing-and-review) and its counter advances by 5,000 EUR as before."""
    batch = insert_ingestion_batch(session)
    for day in days:
        insert_delivery(session, line_id, day, 1_000_000, batch)


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
    closing_id = _header(rolled_back_session, user_id, [facts.flight_id])
    SqlAlchemyAppliedRateRepository(rolled_back_session).save(priced, datetime(2026, 9, 5, 9, 0), user_id, closing_id)

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

def _header(
    session: Session, user_id: int, flight_ids: Sequence[int], year: int = 2026, month: int = 8, as_of: date = AS_OF
) -> int:
    return SqlAlchemyMonthClosingRepository(session).add_closing(
        year, month, datetime(2026, 9, 5, 9, 0), user_id, as_of, flight_ids
    )


def _freeze(
    session: Session,
    month_flights: Sequence[FlightFacts],
    schedules: Sequence[RebateSchedule],
    user_id: int,
    as_of: date = AS_OF,
    opening: Mapping[CounterKey, Decimal] | None = None,
) -> tuple[PricedFlight, ...]:
    priced = price_flights(schedules, PlatformRates(system=Decimal("1.00")), month_flights, as_of, opening)
    closing_id = _header(session, user_id, [item.facts.flight_id for item in priced], as_of=as_of)
    SqlAlchemyAppliedRateRepository(session).save(priced, datetime(2026, 9, 5, 9, 0), user_id, closing_id)
    return priced


def test_saved_rates_keep_every_decision_and_the_breakdown(rolled_back_session):
    line_id = _line(rolled_back_session)
    _deliver_the_contract(rolled_back_session, line_id, date(2026, 8, 10))
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
    _deliver_the_contract(rolled_back_session, line_id, date(2026, 6, 10), date(2026, 7, 10), date(2026, 8, 10))
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
    _deliver_the_contract(rolled_back_session, line_id, date(2026, 7, 10), date(2026, 8, 10))
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


# ---------------------------------------------------------------- delivery counted in the channel's metric

def _dooh_august(session: Session) -> int:
    line_id = _line(session, delivery_metric="ots")
    batch = insert_ingestion_batch(session)
    insert_delivery(session, line_id, date(2026, 8, 10), 7_000, batch, ots=Decimal("140000.2500"))
    insert_delivery(session, line_id, date(2026, 8, 20), 5_000, batch, ots=Decimal("140000.2500"))
    insert_delivery(session, line_id, date(2026, 9, 1), 9_999, batch, ots=Decimal("9999.0000"))  # outside the window
    return line_id


def test_open_ended_dooh_flights_carry_ots_as_delivered_and_the_real_impressions(rolled_back_session: Session) -> None:
    _dooh_august(rolled_back_session)

    (flight,) = SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)

    assert flight.delivered == Decimal("280000.5000") and str(flight.delivered) == "280000.5000"
    assert flight.delivered_impressions == 12_000
    assert flight.delivery_metric == "ots"


def test_list_flights_carries_ots_as_delivered_and_the_real_impressions_for_a_dooh_flight(rolled_back_session: Session) -> None:
    _dooh_august(rolled_back_session)

    (read,) = SqlAlchemyMarginReadRepository(rolled_back_session).list_flights(AS_OF)

    assert read.facts.delivered == Decimal("280000.5000")
    assert read.facts.delivered_impressions == 12_000
    assert read.facts.delivery_metric == "ots"


def test_a_flight_counted_in_impressions_delivers_its_impressions_in_both_figures_in_both_reads(rolled_back_session: Session) -> None:
    line_id = _line(rolled_back_session)
    insert_delivery(
        rolled_back_session, line_id, date(2026, 8, 10), 1_500, insert_ingestion_batch(rolled_back_session),
        ots=Decimal("777.0000"),
    )

    (opened,) = SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)
    (read,) = SqlAlchemyMarginReadRepository(rolled_back_session).list_flights(AS_OF)

    for facts in (opened, read.facts):
        assert (facts.delivered, facts.delivered_impressions, facts.delivery_metric) == (
            Decimal(1_500), 1_500, "impressions",
        )


def test_a_flight_without_delivery_has_zero_delivered_in_its_metric(rolled_back_session: Session) -> None:
    _line(rolled_back_session, delivery_metric="ots")

    (flight,) = SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)

    assert flight.delivered == 0 and isinstance(flight.delivered, Decimal) and flight.delivered_impressions == 0


# ---------------------------------------------------------------- the commitment and the amounts the DSP reports

def _equativ_target_august(session: Session) -> int:
    """The worked example as stored: a target line on Equativ, 1,000,000 at 5.00 €, served 1,100,000 in August."""
    equativ = insert_other_dsp(session, "Equativ")
    line_id = _line(session, campaign_name="Equativ target", dsp_id=equativ)
    session.execute(update(CampaignLineRecord).where(CampaignLineRecord.id == line_id).values(volume_commitment="target"))
    batch = insert_ingestion_batch(session)
    insert_delivery(
        session, line_id, date(2026, 8, 1), 600_000, batch, buyer_spend=Decimal("3000.000001"),
        reported_revenue=Decimal("2400.123456"), third_party_data_cost=Decimal("0.25"),
    )
    insert_delivery(
        session, line_id, date(2026, 8, 31), 500_000, batch, buyer_spend=Decimal("2499.999999"),
        reported_revenue=Decimal("1999.876544"), audience_data_cost=Decimal("1.00"),
    )
    insert_delivery(  # the day after the window: counts for nothing
        session, line_id, date(2026, 9, 1), 9_999, batch, buyer_spend=Decimal(999), reported_revenue=Decimal(999),
        third_party_data_cost=Decimal(999), audience_data_cost=Decimal(999),
    )
    return line_id


def _adform_committed_august(session: Session) -> int:
    line_id = _line(session, campaign_name="Adform committed")
    insert_delivery(session, line_id, date(2026, 8, 10), 700_000, insert_ingestion_batch(session), Decimal("1200.00"))
    return line_id


def _by_line(facts: list[FlightFacts]) -> dict[int, FlightFacts]:
    return {flight.campaign_line_id: flight for flight in facts}


def test_both_reads_return_the_commitment_and_the_reported_amounts_of_a_target_flight_from_the_database(
    rolled_back_session: Session,
) -> None:
    target = _equativ_target_august(rolled_back_session)

    opened = _by_line(SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF))[target]
    read = _by_line([r.facts for r in SqlAlchemyMarginReadRepository(rolled_back_session).list_flights(AS_OF)])[target]

    for facts in (opened, read):
        assert facts.volume_commitment is VolumeCommitment.TARGET
        assert facts.reported_revenue == Decimal("4400.000000")
        assert facts.buyer_spend == Decimal("5500.000000")
        assert facts.data_cost == Decimal("1.250000")  # third-party and audience, summed
        assert facts.delivered_impressions == 1_100_000
        assert all(isinstance(value, Decimal) for value in (facts.reported_revenue, facts.buyer_spend, facts.data_cost))


def test_a_committed_flight_reads_committed_and_zero_reported_amounts(rolled_back_session: Session) -> None:
    committed = _adform_committed_august(rolled_back_session)
    _equativ_target_august(rolled_back_session)

    opened = _by_line(SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF))[committed]
    read = _by_line([r.facts for r in SqlAlchemyMarginReadRepository(rolled_back_session).list_flights(AS_OF)])[committed]

    for facts in (opened, read):
        assert facts.volume_commitment is VolumeCommitment.COMMITTED
        assert (facts.reported_revenue, facts.buyer_spend, facts.data_cost) == (Decimal(0), Decimal(0), Decimal(0))
        assert facts.media_cost == Decimal("1200.00")


def test_the_target_flight_read_from_the_database_is_priced_on_what_equativ_reported(rolled_back_session: Session) -> None:
    target = _equativ_target_august(rolled_back_session)
    (read,) = [r for r in SqlAlchemyMarginReadRepository(rolled_back_session).list_flights(AS_OF)
               if r.facts.campaign_line_id == target]

    (priced,) = price_flights([], PlatformRates(system=Decimal("1.00")), [read.facts], AS_OF)

    assert priced.margin.volume_commitment is VolumeCommitment.TARGET
    assert (priced.margin.revenue, priced.margin.gross_revenue, priced.margin.platform_cost) == (
        Decimal("4400.00"), Decimal("5500.00"), Decimal("1100.00"),
    )
    assert priced.margin.contracted_revenue == Decimal("5000.00")
    assert priced.margin.gross_differs_from_buyer_spend is False
    assert priced.margin.data_cost_reported is True



# ---------------------------------------------------------------- closing headers and snapshots

def _batch(session: Session, dsp_id: int, status: str, finished_at: datetime | None) -> int:
    batch = IngestionBatchRecord(
        dsp_id=dsp_id, route="api", source_file=None, started_at=datetime(2026, 9, 1, 2, 0), finished_at=finished_at,
        status=status, row_count=0, window_start=date(2026, 8, 25), window_end=date(2026, 8, 31),
    )
    session.add(batch)
    session.flush()
    return batch.id


def test_a_closing_header_names_the_month_the_moment_the_user_the_as_of_and_the_latest_succeeded_batch_of_each_dsp(
    rolled_back_session: Session,
) -> None:
    fixture_dsp = seeded_dsp_id(rolled_back_session)
    equativ = insert_other_dsp(rolled_back_session, "Equativ")
    without_batches = insert_other_dsp(rolled_back_session, "A DSP with only a failed batch")
    unrelated = insert_other_dsp(rolled_back_session, "A DSP of no frozen flight")
    lines = [
        _line(rolled_back_session, campaign_name="On the fixture DSP"),
        _line(rolled_back_session, campaign_name="On Equativ", dsp_id=equativ),
        _line(rolled_back_session, campaign_name="On Equativ again", dsp_id=equativ),
        _line(rolled_back_session, campaign_name="Without batches", dsp_id=without_batches),
    ]
    _line(rolled_back_session, campaign_name="Not frozen", dsp_id=unrelated)
    _batch(rolled_back_session, fixture_dsp, "succeeded", datetime(2026, 8, 4, 2, 5))
    latest_fixture = _batch(rolled_back_session, fixture_dsp, "succeeded", datetime(2026, 8, 31, 2, 5))
    _batch(rolled_back_session, fixture_dsp, "failed", datetime(2026, 9, 1, 2, 5))  # later, but failed
    _batch(rolled_back_session, fixture_dsp, "running", None)
    _batch(rolled_back_session, equativ, "succeeded", datetime(2026, 9, 1, 6, 20))
    latest_equativ = _batch(rolled_back_session, equativ, "succeeded", datetime(2026, 9, 1, 6, 20))  # same moment
    _batch(rolled_back_session, without_batches, "failed", datetime(2026, 9, 1, 2, 5))
    _batch(rolled_back_session, unrelated, "succeeded", datetime(2026, 9, 1, 2, 5))
    user_id = insert_user(rolled_back_session)
    facts = SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)
    frozen = [flight.flight_id for flight in facts if flight.campaign_line_id in lines]

    closing_id = SqlAlchemyMonthClosingRepository(rolled_back_session).add_closing(
        2026, 8, datetime(2026, 9, 5, 9, 0), user_id, AS_OF, frozen
    )
    rolled_back_session.expire_all()

    header = rolled_back_session.get(MonthClosingRecord, closing_id)
    assert header is not None
    assert (header.period_year, header.period_month, header.closed_at, header.closed_by, header.as_of) == (
        2026, 8, datetime(2026, 9, 5, 9, 0), user_id, AS_OF,
    )
    batches = rolled_back_session.scalars(
        select(MonthClosingBatchRecord).where(MonthClosingBatchRecord.month_closing_id == closing_id)
    ).all()
    assert {(batch.dsp_id, batch.ingestion_batch_id) for batch in batches} == {
        (fixture_dsp, latest_fixture), (equativ, latest_equativ),
    }


def test_the_headers_of_a_month_are_counted(rolled_back_session: Session) -> None:
    user_id = insert_user(rolled_back_session)
    closings = SqlAlchemyMonthClosingRepository(rolled_back_session)

    assert closings.count_closings(2026, 8) == 0
    _header(rolled_back_session, user_id, [])
    _header(rolled_back_session, user_id, [])
    _header(rolled_back_session, user_id, [], month=9)
    _header(rolled_back_session, user_id, [], year=2025)

    assert (closings.count_closings(2026, 8), closings.count_closings(2026, 9), closings.count_closings(2026, 7)) == (
        2, 1, 0,
    )


def test_save_writes_one_snapshot_per_frozen_flight_under_its_header_holding_what_the_closing_priced(
    rolled_back_session: Session,
) -> None:
    committed = _adform_committed_august(rolled_back_session)
    target = _equativ_target_august(rolled_back_session)
    dooh = _dooh_august(rolled_back_session)
    user_id = insert_user(rolled_back_session)
    facts = SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)

    priced = _freeze(rolled_back_session, facts, [], user_id)
    rolled_back_session.expire_all()

    rows = {row.campaign_line_period_id: row for row in rolled_back_session.scalars(select(AppliedRateRecord))}
    snapshots = {
        snapshot.applied_rate_id: snapshot for snapshot in rolled_back_session.scalars(select(ClosedFlightSnapshotRecord))
    }
    (header,) = rolled_back_session.scalars(select(MonthClosingRecord)).all()
    assert len(snapshots) == len(rows) == len(priced) == 3
    assert {line for line in (committed, target, dooh)} == {item.facts.campaign_line_id for item in priced}
    for item in priced:
        snapshot = snapshots[rows[item.facts.flight_id].id]
        expected = dataclasses.asdict(snapshot_of(item))
        expected["volume_commitment"] = item.facts.volume_commitment.value
        assert snapshot.month_closing_id == header.id
        assert {name: getattr(snapshot, name) for name in expected} == expected


def test_a_target_snapshot_agrees_with_its_applied_rates_row_and_a_committed_one_has_no_gross(
    rolled_back_session: Session,
) -> None:
    committed = _adform_committed_august(rolled_back_session)
    target = _equativ_target_august(rolled_back_session)
    user_id = insert_user(rolled_back_session)
    facts = SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)

    _freeze(rolled_back_session, facts, [], user_id)
    rolled_back_session.expire_all()

    by_line = {
        line_id: (row, snapshot)
        for row, snapshot, line_id in rolled_back_session.execute(
            select(AppliedRateRecord, ClosedFlightSnapshotRecord, CampaignLinePeriodRecord.campaign_line_id)
            .join(ClosedFlightSnapshotRecord, ClosedFlightSnapshotRecord.applied_rate_id == AppliedRateRecord.id)
            .join(CampaignLinePeriodRecord, CampaignLinePeriodRecord.id == AppliedRateRecord.campaign_line_period_id)
        ).tuples()
    }
    target_row, target_snapshot = by_line[target]
    assert (target_snapshot.revenue, target_snapshot.gross_revenue) == (
        target_row.revenue_amount, target_row.rebate_base_amount,
    ) == (Decimal("4400.00"), Decimal("5500.00"))
    assert target_snapshot.volume_commitment == "target"
    committed_row, committed_snapshot = by_line[committed]
    assert (committed_snapshot.gross_revenue, committed_row.rebate_base_amount) == (None, None)
    assert committed_snapshot.volume_commitment == "committed"


# ---------------------------------------------------------------- a closed flight is read with its snapshot

def _read(session: Session, line_id: int) -> ReadFlight:
    (read,) = [r for r in SqlAlchemyMarginReadRepository(session).list_flights(AS_OF) if r.facts.campaign_line_id == line_id]
    return read


def test_list_flights_returns_the_snapshot_of_a_frozen_flight_with_its_rates(rolled_back_session: Session) -> None:
    committed = _adform_committed_august(rolled_back_session)
    target = _equativ_target_august(rolled_back_session)
    user_id = insert_user(rolled_back_session)
    facts = SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)
    priced = {item.facts.campaign_line_id: item for item in _freeze(rolled_back_session, facts, [], user_id)}
    rolled_back_session.expire_all()

    for line_id in (committed, target):
        frozen = _read(rolled_back_session, line_id).frozen
        assert frozen is not None
        assert frozen.snapshot == snapshot_of(priced[line_id])
        assert frozen.platform_rate == priced[line_id].platform.rate
        assert frozen.rebate_amount == priced[line_id].rebate.rebate


def test_a_flight_not_frozen_has_no_snapshot(rolled_back_session: Session) -> None:
    line_id = _adform_committed_august(rolled_back_session)

    assert _read(rolled_back_session, line_id).frozen is None


def test_the_current_delivery_of_a_closed_flight_is_summed_in_its_frozen_metric_after_its_channel_changes(
    rolled_back_session: Session,
) -> None:
    closed = _dooh_august(rolled_back_session)
    user_id = insert_user(rolled_back_session)
    (facts,) = SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)
    _freeze(rolled_back_session, [facts], [], user_id)
    closed_line = rolled_back_session.get(CampaignLineRecord, closed)
    assert closed_line is not None
    channel_id = closed_line.channel_id
    still_open = add_line_to_campaign(rolled_back_session, closed, 2)  # same channel, not frozen
    insert_delivery(rolled_back_session, still_open, date(2026, 8, 10), 3_000, insert_ingestion_batch(rolled_back_session),
                    ots=Decimal("60000.0000"))
    insert_delivery(rolled_back_session, closed, date(2026, 8, 25), 1_000, insert_ingestion_batch(rolled_back_session),
                    ots=Decimal("20000.0000"))  # restated after closing

    rolled_back_session.execute(update(ChannelRecord).where(ChannelRecord.id == channel_id).values(delivery_metric="impressions"))
    rolled_back_session.flush()

    read = _read(rolled_back_session, closed)
    assert read.frozen is not None and read.frozen.snapshot.delivery_metric == "ots"
    assert (read.facts.delivery_metric, read.facts.delivered, read.facts.delivered_impressions) == (
        "ots", Decimal("300000.5000"), 13_000,
    )
    other = _read(rolled_back_session, still_open)
    assert (other.facts.delivery_metric, other.facts.delivered) == ("impressions", Decimal("3000.0000"))


# ---------------------------------------------------------------- the carry-over and the adjustment of a flight


def _flight_id(session: Session, line_id: int, index: int = 0) -> int:
    return session.scalars(
        select(CampaignLinePeriodRecord.id).where(CampaignLinePeriodRecord.campaign_line_id == line_id)
        .order_by(CampaignLinePeriodRecord.flight_start)
    ).all()[index]


def _adjust(session: Session, flight_id: int, user_id: int, basis: str, amount: str | None = None) -> None:
    session.add(FlightBillingAdjustmentRecord(
        campaign_line_period_id=flight_id, basis=basis, amount=None if amount is None else Decimal(amount),
        reason="Acuerdo con la agencia", created_by=user_id,
    ))
    session.flush()


def _both_read(session: Session) -> dict[str, FlightFacts]:
    """The facts of the only flight as the closing reads them and as the margin read does."""
    (closing,) = SqlAlchemyMarginFlightRepository(session).open_ended_flights(2026, 8, AS_OF)
    (read,) = SqlAlchemyMarginReadRepository(session).list_flights(AS_OF)
    return {"closing": closing, "read": read.facts}


def test_a_flight_without_a_carry_over_or_an_adjustment_carries_none(rolled_back_session: Session) -> None:
    _line(rolled_back_session)

    for facts in _both_read(rolled_back_session).values():
        assert (facts.carryover, facts.carryover_billable, facts.adjustment) == (0, False, None)


def test_a_flight_carries_its_carry_over_and_whether_it_is_billable(rolled_back_session: Session) -> None:
    line_id = _line(rolled_back_session)
    user_id = insert_user(rolled_back_session)
    rolled_back_session.execute(update(CampaignLinePeriodRecord).values(
        carryover=100_000, carryover_reason="Recuperar", carryover_set_by=user_id, carryover_set_at=datetime(2026, 8, 2),
        carryover_billable=True, carryover_billable_set_by=user_id, carryover_billable_set_at=datetime(2026, 8, 3),
    ))
    assert line_id

    for facts in _both_read(rolled_back_session).values():
        assert (facts.carryover, facts.carryover_billable) == (100_000, True)


def test_a_flight_carries_the_adjustment_in_force(rolled_back_session: Session) -> None:
    line_id = _line(rolled_back_session)
    user_id = insert_user(rolled_back_session)
    _adjust(rolled_back_session, _flight_id(rolled_back_session, line_id), user_id, "contracted")

    for facts in _both_read(rolled_back_session).values():
        assert facts.adjustment == BillingAdjustment(BillingBasis.CONTRACTED, None)


def test_the_latest_adjustment_by_id_is_the_one_in_force(rolled_back_session: Session) -> None:
    line_id = _line(rolled_back_session)
    flight_id = _flight_id(rolled_back_session, line_id)
    user_id = insert_user(rolled_back_session)
    _adjust(rolled_back_session, flight_id, user_id, "contracted")
    _adjust(rolled_back_session, flight_id, user_id, "custom", "4200.00")

    for facts in _both_read(rolled_back_session).values():
        assert facts.adjustment == BillingAdjustment(BillingBasis.CUSTOM, Decimal("4200.00"))


def test_an_adjustment_to_the_minimum_returns_the_flight_to_the_rule_and_is_read_as_such(rolled_back_session: Session) -> None:
    line_id = _line(rolled_back_session)
    flight_id = _flight_id(rolled_back_session, line_id)
    user_id = insert_user(rolled_back_session)
    _adjust(rolled_back_session, flight_id, user_id, "contracted")
    _adjust(rolled_back_session, flight_id, user_id, "minimum")

    for facts in _both_read(rolled_back_session).values():
        assert facts.adjustment == BillingAdjustment(BillingBasis.MINIMUM, None)


def test_the_adjustment_of_one_flight_does_not_reach_another(rolled_back_session: Session) -> None:
    first = _line(rolled_back_session, campaign_name="Adjusted")
    second = add_line_to_campaign(rolled_back_session, first, 2)
    user_id = insert_user(rolled_back_session)
    _adjust(rolled_back_session, _flight_id(rolled_back_session, first), user_id, "delivered")

    by_line = _by_line(SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF))

    assert by_line[first].adjustment == BillingAdjustment(BillingBasis.DELIVERED, None)
    assert by_line[second].adjustment is None


def test_the_facts_of_a_frozen_flight_are_still_read_with_their_adjustment(rolled_back_session: Session) -> None:
    line_id = _line(rolled_back_session)
    user_id = insert_user(rolled_back_session)
    _adjust(rolled_back_session, _flight_id(rolled_back_session, line_id), user_id, "contracted")
    (facts,) = SqlAlchemyMarginFlightRepository(rolled_back_session).open_ended_flights(2026, 8, AS_OF)
    _freeze(rolled_back_session, [facts], [], user_id)

    (read,) = SqlAlchemyMarginReadRepository(rolled_back_session).list_flights(AS_OF)

    assert read.frozen is not None
    assert read.facts.adjustment == BillingAdjustment(BillingBasis.CONTRACTED, None)
