"""Closing a month: it freezes the rates of the flights that ended in it, once, in order, and all or nothing."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.application.services import margin_closing_service
from app.application.services.margin_closing_service import MarginClosingService
from app.domain.exceptions import PreviousMonthOpenError
from app.domain.services.flight_margin import calculate_flight_margin
from app.domain.services.priced_flights import price_flights
from app.domain.value_objects.margin import FlightEconomics
from app.infrastructure.persistence.models.campaign import CampaignLineRecord, CampaignRecord
from app.infrastructure.persistence.models.margin import (
    AppliedRateBracketRecord,
    AppliedRateRecord,
    PlatformRateSettingRecord,
    RebateBracketRecord,
    RebateScheduleRecord,
)
from app.infrastructure.persistence.models.masters import AgencyRecord
from app.infrastructure.persistence.repositories import sqlalchemy_margin_repositories
from app.infrastructure.persistence.repositories.sqlalchemy_margin_repositories import (
    SqlAlchemyMarginClosingTransaction,
)
from tests.fixtures.delivery_data import (
    add_line_to_campaign,
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    insert_user,
    replace_flights,
)

SEPTEMBER_FIRST = date(2026, 9, 1)  # D; as_of is 31 August, so August is over


def _service(session, today: date = SEPTEMBER_FIRST) -> MarginClosingService:
    return MarginClosingService(
        SqlAlchemyMarginClosingTransaction(session), today=lambda: today, now=lambda: datetime(2026, 9, 1, 8, 30)
    )


def _group_of(session, line_id: int) -> int:
    line = session.get(CampaignLineRecord, line_id)
    campaign = session.get(CampaignRecord, line.campaign_id)
    return session.get(AgencyRecord, campaign.agency_id).holding_group_id


def _schedule(session, group_id: int, *brackets: tuple[str, str | None, str]) -> int:
    schedule = RebateScheduleRecord(holding_group_id=group_id, valid_from=date(2026, 1, 1))
    session.add(schedule)
    session.flush()
    for position, (lower, upper, rate) in enumerate(brackets, start=1):
        session.add(RebateBracketRecord(
            rebate_schedule_id=schedule.id, position=position, lower=Decimal(lower),
            upper=None if upper is None else Decimal(upper), rate=Decimal(rate)))
    session.flush()
    return schedule.id


def _rows(session) -> list[AppliedRateRecord]:
    return list(session.scalars(select(AppliedRateRecord).order_by(AppliedRateRecord.id)))


def _august_lines(session, count: int = 3) -> list[int]:
    first = insert_campaign_line(session)
    lines = [first] + [add_line_to_campaign(session, first, number) for number in range(2, count + 1)]
    return lines


@pytest.fixture
def user_id(rolled_back_session) -> int:
    return insert_user(rolled_back_session, "closer@example.com")


def test_closing_freezes_one_row_per_ended_flight(rolled_back_session, user_id):
    lines = _august_lines(rolled_back_session)
    _schedule(rolled_back_session, _group_of(rolled_back_session, lines[0]), ("0", None, "0.25"))

    result = _service(rolled_back_session).close_month(2026, 8, user_id)

    assert (result.year, result.month, result.closed, result.already_closed) == (2026, 8, 3, 0)
    rows = _rows(rolled_back_session)
    assert len(rows) == 3
    assert {row.closed_by for row in rows} == {user_id}
    assert {row.closed_at for row in rows} == {datetime(2026, 9, 1, 8, 30)}


def test_a_flight_that_has_not_ended_gets_no_row(rolled_back_session, user_id):
    line_id = insert_campaign_line(rolled_back_session, start_date=date(2026, 8, 1), end_date=date(2026, 8, 31))
    replace_flights(rolled_back_session, line_id, [(date(2026, 8, 1), date(2026, 8, 31))])

    result = _service(rolled_back_session, today=date(2026, 8, 31)).close_month(2026, 8, user_id)

    assert result.closed == 0
    assert _rows(rolled_back_session) == []


def test_the_day_before_today_is_the_last_day_counted(rolled_back_session, user_id):
    insert_campaign_line(rolled_back_session)

    assert _service(rolled_back_session, today=date(2026, 8, 31)).close_month(2026, 8, user_id).closed == 0
    assert _service(rolled_back_session, today=date(2026, 9, 1)).close_month(2026, 8, user_id).closed == 1


def test_closing_twice_neither_adds_nor_changes_a_row(rolled_back_session, user_id):
    _august_lines(rolled_back_session)
    service = _service(rolled_back_session)
    service.close_month(2026, 8, user_id)
    before = [(r.id, r.rebate_amount, r.closed_at, r.position_after) for r in _rows(rolled_back_session)]

    second = _service(rolled_back_session, today=date(2026, 9, 20)).close_month(2026, 8, user_id)

    assert (second.closed, second.already_closed) == (0, 3)
    assert [(r.id, r.rebate_amount, r.closed_at, r.position_after) for r in _rows(rolled_back_session)] == before


def test_a_month_with_no_ended_flights_closes_nothing_and_writes_nothing(rolled_back_session, user_id):
    result = _service(rolled_back_session).close_month(2026, 3, user_id)

    assert (result.closed, result.already_closed) == (0, 0)
    assert _rows(rolled_back_session) == []


def test_an_earlier_open_month_blocks_the_closing_and_is_named(rolled_back_session, user_id):
    line_id = insert_campaign_line(rolled_back_session, start_date=date(2026, 6, 1), end_date=date(2026, 8, 31))
    replace_flights(rolled_back_session, line_id, [
        (date(2026, 6, 1), date(2026, 6, 30)), (date(2026, 7, 1), date(2026, 7, 31)), (date(2026, 8, 1), date(2026, 8, 31)),
    ])

    with pytest.raises(PreviousMonthOpenError) as raised:
        _service(rolled_back_session).close_month(2026, 8, user_id)

    assert (raised.value.year, raised.value.month) == (2026, 6)
    assert "2026-06" in str(raised.value)
    assert _rows(rolled_back_session) == []


def test_months_close_in_order(rolled_back_session, user_id):
    line_id = insert_campaign_line(rolled_back_session, start_date=date(2026, 6, 1), end_date=date(2026, 8, 31))
    replace_flights(rolled_back_session, line_id, [
        (date(2026, 6, 1), date(2026, 6, 30)), (date(2026, 7, 1), date(2026, 7, 31)), (date(2026, 8, 1), date(2026, 8, 31)),
    ])
    service = _service(rolled_back_session)

    assert service.close_month(2026, 6, user_id).closed == 1
    assert service.close_month(2026, 7, user_id).closed == 1
    assert service.close_month(2026, 8, user_id).closed == 1


def test_an_earlier_year_does_not_block(rolled_back_session, user_id):
    line_id = insert_campaign_line(rolled_back_session, start_date=date(2025, 11, 1), end_date=date(2026, 8, 31))
    replace_flights(rolled_back_session, line_id, [(date(2025, 12, 1), date(2025, 12, 31)), (date(2026, 8, 1), date(2026, 8, 31))])

    assert _service(rolled_back_session).close_month(2026, 8, user_id).closed == 1


def test_the_months_flights_reach_the_engine_by_start_then_id(rolled_back_session, user_id, monkeypatch):
    lines = _august_lines(rolled_back_session)
    seen: list[list[tuple[date, int]]] = []
    original = margin_closing_service.price_flights

    def spy(schedules, platform_rates, flights, as_of, opening_positions=None):
        seen.append([(f.flight_start, f.flight_id) for f in flights])
        return original(schedules, platform_rates, flights, as_of, opening_positions)

    monkeypatch.setattr(margin_closing_service, "price_flights", spy)

    _service(rolled_back_session).close_month(2026, 8, user_id)

    assert len(seen) == 1 and len(seen[0]) == len(lines)
    assert seen[0] == sorted(seen[0])


def test_the_month_is_locked_before_anything_is_read(rolled_back_session, user_id):
    insert_campaign_line(rolled_back_session)
    transaction = SqlAlchemyMarginClosingTransaction(rolled_back_session)
    calls: list[str] = []
    original_lock, original_open = transaction.lock_month, transaction.flights.open_ended_flights
    transaction.lock_month = lambda year, month: (calls.append(f"lock {year}-{month}"), original_lock(year, month))[1]  # type: ignore[method-assign]
    transaction.flights.open_ended_flights = lambda *a: (calls.append("read"), original_open(*a))[1]  # type: ignore[method-assign]

    MarginClosingService(transaction, today=lambda: SEPTEMBER_FIRST, now=lambda: datetime(2026, 9, 1)).close_month(2026, 8, user_id)

    assert calls[:2] == ["lock 2026-8", "read"]


def test_a_failure_halfway_leaves_no_row(rolled_back_session, user_id, monkeypatch):
    _august_lines(rolled_back_session)
    rolled_back_session.commit()  # the fixtures stay; only the closing may be undone
    original_save = sqlalchemy_margin_repositories.SqlAlchemyAppliedRateRepository.save

    def failing_save(self, priced, closed_at, closed_by):
        original_save(self, priced[:1], closed_at, closed_by)  # the first flight is written ...
        raise RuntimeError("forced failure")                   # ... and then the closing fails

    monkeypatch.setattr(sqlalchemy_margin_repositories.SqlAlchemyAppliedRateRepository, "save", failing_save)

    with pytest.raises(RuntimeError, match="forced failure"):
        _service(rolled_back_session).close_month(2026, 8, user_id)

    assert _rows(rolled_back_session) == []
    assert rolled_back_session.scalar(select(func.count()).select_from(AppliedRateBracketRecord)) == 0


def test_the_next_closing_starts_from_the_frozen_position_and_does_not_price_frozen_flights_again(rolled_back_session, user_id):
    line_id = insert_campaign_line(rolled_back_session, start_date=date(2026, 7, 1), end_date=date(2026, 8, 31))
    replace_flights(rolled_back_session, line_id, [(date(2026, 7, 1), date(2026, 7, 31)), (date(2026, 8, 1), date(2026, 8, 31))])
    group_id = _group_of(rolled_back_session, line_id)
    schedule = RebateScheduleRecord(holding_group_id=group_id, valid_from=date(2026, 1, 1))
    rolled_back_session.add(schedule)
    rolled_back_session.flush()
    rolled_back_session.add_all([
        RebateBracketRecord(rebate_schedule_id=schedule.id, position=1, lower=Decimal(0), upper=Decimal(6000), rate=Decimal("0.10")),
        RebateBracketRecord(rebate_schedule_id=schedule.id, position=2, lower=Decimal(6000), upper=None, rate=Decimal("0.30")),
    ])
    rolled_back_session.flush()
    service = _service(rolled_back_session)
    service.close_month(2026, 7, user_id)
    july = _rows(rolled_back_session)[0]
    july_snapshot = (july.rebate_amount, july.position_before, july.position_after)

    service.close_month(2026, 8, user_id)
    august = _rows(rolled_back_session)[1]

    assert august.position_before == Decimal("5000.00")
    assert august.rebate_amount == Decimal("1000.00") * Decimal("0.10") + Decimal("4000.00") * Decimal("0.30")
    rolled_back_session.refresh(july)
    assert (july.rebate_amount, july.position_before, july.position_after) == july_snapshot


def test_a_schedule_edited_after_closing_does_not_move_the_frozen_row(rolled_back_session, user_id):
    lines = _august_lines(rolled_back_session, count=1)
    group_id = _group_of(rolled_back_session, lines[0])
    schedule_id = _schedule(rolled_back_session, group_id, ("0", None, "0.25"))
    _service(rolled_back_session).close_month(2026, 8, user_id)
    frozen = _rows(rolled_back_session)[0].rebate_amount

    rolled_back_session.query(RebateBracketRecord).filter_by(rebate_schedule_id=schedule_id).update({"rate": Decimal("0.90")})
    rolled_back_session.flush()
    _service(rolled_back_session, today=date(2026, 9, 30)).close_month(2026, 8, user_id)

    rolled_back_session.expire_all()
    assert _rows(rolled_back_session)[0].rebate_amount == frozen == Decimal("1250.000000000000")


def test_the_platform_rate_in_force_is_frozen_with_its_override(rolled_back_session, user_id):
    lines = _august_lines(rolled_back_session, count=1)
    line = rolled_back_session.get(CampaignLineRecord, lines[0])
    campaign = rolled_back_session.get(CampaignRecord, line.campaign_id)
    rolled_back_session.add(PlatformRateSettingRecord(
        level="agency", agency_id=campaign.agency_id, rate_per_thousand=Decimal("1.40"), created_by=user_id))
    rolled_back_session.flush()

    _service(rolled_back_session).close_month(2026, 8, user_id)

    assert _rows(rolled_back_session)[0].platform_rate == Decimal("1.40")


def test_pending_close_figures_are_the_figures_closing_freezes(rolled_back_session, user_id, monkeypatch):
    """Three flights of one counter, read as a pending-close read would, then closed: the same to the cent."""
    lines = _august_lines(rolled_back_session, count=3)
    group_id = _group_of(rolled_back_session, lines[0])
    schedule = RebateScheduleRecord(holding_group_id=group_id, valid_from=date(2026, 1, 1))
    rolled_back_session.add(schedule)
    rolled_back_session.flush()
    rolled_back_session.add_all([
        RebateBracketRecord(rebate_schedule_id=schedule.id, position=1, lower=Decimal(0), upper=Decimal(6000), rate=Decimal("0.15")),
        RebateBracketRecord(rebate_schedule_id=schedule.id, position=2, lower=Decimal(6000), upper=None, rate=Decimal("0.2")),
    ])
    batch = insert_ingestion_batch(rolled_back_session)
    for index, line_id in enumerate(lines, start=1):
        insert_delivery(rolled_back_session, line_id, date(2026, 8, 10), 100_000 * index, batch, Decimal("123.456789") * index)
    rolled_back_session.flush()

    transaction = SqlAlchemyMarginClosingTransaction(rolled_back_session)
    facts = transaction.flights.open_ended_flights(2026, 8, date(2026, 8, 31))
    pending = price_flights(
        transaction.schedules.list_schedules(), transaction.platform_rates.current_rates(), facts, date(2026, 8, 31),
        transaction.applied_rates.opening_positions(2026),
    )
    called: list[int] = []
    original = margin_closing_service.price_flights
    monkeypatch.setattr(margin_closing_service, "price_flights", lambda *a, **k: (called.append(1), original(*a, **k))[1])

    MarginClosingService(transaction, today=lambda: SEPTEMBER_FIRST, now=lambda: datetime(2026, 9, 1)).close_month(2026, 8, user_id)

    assert called == [1]  # the closing goes through the same domain function the reads use
    frozen = {row.campaign_line_period_id: row for row in _rows(rolled_back_session)}
    assert len(frozen) == 3
    for item in pending:
        row = frozen[item.facts.flight_id]
        margin_from_frozen = calculate_flight_margin(
            FlightEconomics(
                flight_start=item.facts.flight_start, flight_end=item.facts.flight_end,
                contracted_impressions=item.facts.contracted_impressions, sale_cpm=item.facts.sale_cpm,
                delivered_impressions=item.facts.delivered_impressions, media_cost=item.facts.media_cost,
                rebate_amount=row.rebate_amount, platform_rate=row.platform_rate,
            ),
            date(2026, 8, 31),
        )
        assert margin_from_frozen == item.margin
        assert margin_from_frozen.margin == item.margin.margin
        assert row.position_before == item.rebate.position_before


def test_changing_the_system_rate_after_closing_does_not_move_the_frozen_flight(rolled_back_session, user_id):
    _august_lines(rolled_back_session, count=1)
    _service(rolled_back_session).close_month(2026, 8, user_id)
    frozen = _rows(rolled_back_session)[0]
    assert frozen.platform_rate == Decimal("1.000000")

    rolled_back_session.add(PlatformRateSettingRecord(level="system", rate_per_thousand=Decimal("2.50"), created_by=user_id))
    rolled_back_session.flush()
    _service(rolled_back_session, today=date(2026, 9, 30)).close_month(2026, 8, user_id)

    rolled_back_session.refresh(frozen)
    assert frozen.platform_rate == Decimal("1.000000")
    assert len(_rows(rolled_back_session)) == 1
