"""Closing a month: it freezes the rates of the flights that ended in it, once, in order, and all or nothing."""

import dataclasses
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from app.application.services import margin_closing_service
from app.application.services.margin_query_service import MarginQueryService
from app.application.services.delivery_ingestion_service import DeliveryIngestionService
from app.application.services.line_mapping_removal_service import LineMappingRemovalService
from app.application.services.billing_adjustment_service import BillingAdjustmentService
from app.application.services.margin_closing_service import MarginClosingService
from app.application.services.monthly_review_service import MonthlyReviewService
from app.domain.exceptions import MonthDeliveryNotLoadedError, MonthNotReviewedError, PreviousMonthOpenError
from app.domain.services.closed_flight import margin_from_snapshot, snapshot_of
from app.domain.services.flight_margin import calculate_flight_margin
from app.domain.services.priced_flights import price_flights
from app.domain.value_objects.closed_flight import ClosedDeliveryCheck, ClosedFlightSnapshot
from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey
from app.domain.value_objects.margin import FlightMargin
from app.domain.value_objects.margin_report import FlightReport, FlightState, MarginReport
from app.domain.value_objects.billing import BillingBasis
from app.domain.value_objects.review import ReviewState
from app.domain.value_objects.volume_commitment import VolumeCommitment
from app.infrastructure.dsp.equativ_delivery_client import EquativDeliveryClient
from app.infrastructure.persistence.models.campaign import CampaignLinePeriodRecord, CampaignLineRecord, CampaignRecord
from app.infrastructure.persistence.models.delivery import IngestionBatchRecord
from app.infrastructure.persistence.models.margin import (
    AppliedRateBracketRecord,
    AppliedRateRecord,
    ClosedFlightSnapshotRecord,
    MonthClosingBatchRecord,
    MonthClosingRecord,
    PlatformRateSettingRecord,
    RebateBracketRecord,
    RebateScheduleRecord,
)
from app.infrastructure.persistence.models.masters import AgencyRecord, ChannelRecord
from app.infrastructure.persistence.repositories import sqlalchemy_margin_repositories
from app.infrastructure.persistence.repositories.sqlalchemy_margin_repositories import (
    SqlAlchemyAppliedRateRepository,
    SqlAlchemyMarginClosingTransaction,
    SqlAlchemyMarginReadRepository,
    SqlAlchemyPlatformRateRepository,
    SqlAlchemyRebateScheduleRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_line_mapping_removal_repository import (
    SqlAlchemyLineMappingRemovalRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_billing_adjustment_repository import (
    SqlAlchemyBillingAdjustmentTransaction,
)
from app.infrastructure.persistence.repositories.sqlalchemy_review_repository import (
    SqlAlchemyMonthlyReviewTransaction,
)
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from scripts.run_ingestion import main as run_ingestion
from tests.fixtures.delivery_data import (
    add_line_to_campaign,
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    insert_mapping,
    insert_other_dsp,
    insert_user,
    replace_flights,
    seeded_dsp_id,
)
from tests.fixtures.delivery_rows import dsp_row
from tests.fixtures.dsp_delivery_client import InMemoryDspDeliveryClient
from tests.fixtures.fake_equativ import FakeEquativ, package_row
from tests.fixtures.flight_inputs import flight_economics
from tests.fixtures.margin_data import load_months_last_day, make_month_closable, review_month

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


def _headers(session: Session) -> list[MonthClosingRecord]:
    return list(session.scalars(select(MonthClosingRecord).order_by(MonthClosingRecord.id)))


def _snapshots(session: Session) -> list[ClosedFlightSnapshotRecord]:
    return list(session.scalars(select(ClosedFlightSnapshotRecord).order_by(ClosedFlightSnapshotRecord.id)))


def _snapshot_of_record(record: ClosedFlightSnapshotRecord) -> ClosedFlightSnapshot:
    columns = {field.name: getattr(record, field.name) for field in dataclasses.fields(ClosedFlightSnapshot)}
    return ClosedFlightSnapshot(**{**columns, "volume_commitment": VolumeCommitment(record.volume_commitment)})


def _read_margin(session: Session, today: date) -> MarginReport:
    return MarginQueryService(
        SqlAlchemyMarginReadRepository(session), SqlAlchemyRebateScheduleRepository(session),
        SqlAlchemyPlatformRateRepository(session), SqlAlchemyAppliedRateRepository(session), today=lambda: today,
    ).get_margin()


def _flight_reports(report: MarginReport, line_id: int) -> list[FlightReport]:
    return [
        flight for campaign in report.campaigns for line in campaign.lines for flight in line.flights
        if line.campaign_line_id == line_id
    ]


def _august_lines(session, count: int = 3, deliver_the_contract: bool = True) -> list[int]:
    """Lines of one August flight each. Left out, each delivers its 1,000,000 contracted impressions and so bills its
    contracted sale, 5,000.00 EUR (committed-billing-and-review); a test that stores its own delivery passes False."""
    first = insert_campaign_line(session)
    lines = [first] + [add_line_to_campaign(session, first, number) for number in range(2, count + 1)]
    if deliver_the_contract:
        batch = insert_ingestion_batch(session)
        for line_id in lines:
            insert_delivery(session, line_id, date(2026, 8, 10), 1_000_000, batch)
    return lines


@pytest.fixture
def user_id(rolled_back_session) -> int:
    return insert_user(rolled_back_session, "closer@example.com")


def test_closing_freezes_one_row_per_ended_flight(rolled_back_session, user_id):
    lines = _august_lines(rolled_back_session)
    _schedule(rolled_back_session, _group_of(rolled_back_session, lines[0]), ("0", None, "0.25"))

    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
    result = _service(rolled_back_session).close_month(2026, 8, user_id)

    assert (result.year, result.month, result.closed, result.already_closed) == (2026, 8, 3, 0)
    rows = _rows(rolled_back_session)
    assert len(rows) == 3
    assert {row.closed_by for row in rows} == {user_id}
    assert {row.closed_at for row in rows} == {datetime(2026, 9, 1, 8, 30)}


def test_closing_writes_one_header_and_one_snapshot_per_frozen_flight_under_it(
    rolled_back_session: Session, user_id: int
) -> None:
    _august_lines(rolled_back_session)

    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
    result = _service(rolled_back_session).close_month(2026, 8, user_id)

    assert result.closings == 1
    (header,) = _headers(rolled_back_session)
    assert (header.period_year, header.period_month, header.closed_at, header.closed_by, header.as_of) == (
        2026, 8, datetime(2026, 9, 1, 8, 30), user_id, date(2026, 8, 31),
    )
    snapshots = _snapshots(rolled_back_session)
    assert sorted(snapshot.applied_rate_id for snapshot in snapshots) == [row.id for row in _rows(rolled_back_session)]
    assert {snapshot.month_closing_id for snapshot in snapshots} == {header.id}


def test_a_flight_that_has_not_ended_gets_no_row_and_its_month_is_refused(rolled_back_session, user_id):
    # committed-billing-and-review: the month is refused while a flight runs, instead of closing the ended ones.
    line_id = insert_campaign_line(rolled_back_session, start_date=date(2026, 8, 1), end_date=date(2026, 8, 31))
    replace_flights(rolled_back_session, line_id, [(date(2026, 8, 1), date(2026, 8, 31))])
    make_month_closable(rolled_back_session, 2026, 8, user_id, date(2026, 8, 31))

    with pytest.raises(MonthNotReviewedError):
        _service(rolled_back_session, today=date(2026, 8, 31)).close_month(2026, 8, user_id)

    assert _rows(rolled_back_session) == []


def test_the_day_before_today_is_the_last_day_counted(rolled_back_session, user_id):
    insert_campaign_line(rolled_back_session)
    make_month_closable(rolled_back_session, 2026, 8, user_id, date(2026, 8, 31))
    rolled_back_session.commit()  # the refused closing rolls back what was only flushed

    with pytest.raises(MonthNotReviewedError):  # on 31 August its flight, ending that day, is still running
        _service(rolled_back_session, today=date(2026, 8, 31)).close_month(2026, 8, user_id)
    make_month_closable(rolled_back_session, 2026, 8, user_id, date(2026, 9, 1))
    assert _service(rolled_back_session, today=date(2026, 9, 1)).close_month(2026, 8, user_id).closed == 1


def test_closing_twice_neither_adds_nor_changes_a_row(rolled_back_session, user_id):
    _august_lines(rolled_back_session)
    service = _service(rolled_back_session)
    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
    service.close_month(2026, 8, user_id)
    before = [(r.id, r.rebate_amount, r.closed_at, r.position_after) for r in _rows(rolled_back_session)]

    second = _service(rolled_back_session, today=date(2026, 9, 20)).close_month(2026, 8, user_id)

    assert (second.closed, second.already_closed, second.closings) == (0, 3, 1)
    assert [(r.id, r.rebate_amount, r.closed_at, r.position_after) for r in _rows(rolled_back_session)] == before
    assert len(_headers(rolled_back_session)) == 1
    assert len(_snapshots(rolled_back_session)) == 3


def test_a_month_with_no_ended_flights_closes_nothing_and_writes_nothing(rolled_back_session, user_id):
    make_month_closable(rolled_back_session, 2026, 3, user_id, SEPTEMBER_FIRST)
    result = _service(rolled_back_session).close_month(2026, 3, user_id)

    assert (result.closed, result.already_closed, result.closings) == (0, 0, 0)
    assert _rows(rolled_back_session) == []
    assert _headers(rolled_back_session) == []
    assert _snapshots(rolled_back_session) == []


def test_a_closing_that_freezes_nothing_writes_no_header(rolled_back_session: Session, user_id: int) -> None:
    # committed-billing-and-review: a month with a running flight is refused, so nothing is frozen with no header
    # only when every flight of the month is frozen already.
    _august_lines(rolled_back_session, count=1)
    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
    _service(rolled_back_session).close_month(2026, 8, user_id)

    result = _service(rolled_back_session, today=date(2026, 9, 20)).close_month(2026, 8, user_id)

    assert (result.closed, result.closings) == (0, 1)
    assert len(_headers(rolled_back_session)) == 1


def test_a_flight_registered_in_a_closed_month_is_frozen_by_a_second_closing_under_a_second_header(
    rolled_back_session: Session, user_id: int
) -> None:
    lines = _august_lines(rolled_back_session)
    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
    _service(rolled_back_session).close_month(2026, 8, user_id)
    rolled_back_session.expire_all()
    first = [
        (row.id, row.rebate_amount, row.position_after, row.closed_at) for row in _rows(rolled_back_session)
    ], [
        (snapshot.id, snapshot.applied_rate_id, snapshot.month_closing_id, snapshot.margin)
        for snapshot in _snapshots(rolled_back_session)
    ], [(header.id, header.closed_at, header.as_of) for header in _headers(rolled_back_session)]
    late = add_line_to_campaign(rolled_back_session, lines[0], 4)

    second = MarginClosingService(
        SqlAlchemyMarginClosingTransaction(rolled_back_session), today=lambda: date(2026, 9, 20),
        now=lambda: datetime(2026, 9, 20, 10, 0),
    ).close_month(2026, 8, user_id)
    rolled_back_session.expire_all()

    assert (second.closed, second.already_closed, second.closings) == (1, 3, 2)
    headers = _headers(rolled_back_session)
    assert [(h.closed_at, h.as_of) for h in headers[1:]] == [(datetime(2026, 9, 20, 10, 0), date(2026, 9, 19))]
    (late_snapshot,) = [s for s in _snapshots(rolled_back_session) if s.month_closing_id == headers[1].id]
    late_row = rolled_back_session.get(AppliedRateRecord, late_snapshot.applied_rate_id)
    assert late_row is not None
    late_flight = rolled_back_session.get(CampaignLinePeriodRecord, late_row.campaign_line_period_id)
    assert late_flight is not None and late_flight.campaign_line_id == late
    rows, snapshots = _rows(rolled_back_session), _snapshots(rolled_back_session)
    assert [(r.id, r.rebate_amount, r.position_after, r.closed_at) for r in rows[:3]] == first[0]
    assert [(s.id, s.applied_rate_id, s.month_closing_id, s.margin) for s in snapshots[:3]] == first[1]
    assert [(h.id, h.closed_at, h.as_of) for h in headers[:1]] == first[2]


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

    for month in (6, 7, 8):
        make_month_closable(rolled_back_session, 2026, month, user_id, SEPTEMBER_FIRST)
        assert service.close_month(2026, month, user_id).closed == 1


def test_an_earlier_year_does_not_block(rolled_back_session, user_id):
    line_id = insert_campaign_line(rolled_back_session, start_date=date(2025, 11, 1), end_date=date(2026, 8, 31))
    replace_flights(rolled_back_session, line_id, [(date(2025, 12, 1), date(2025, 12, 31)), (date(2026, 8, 1), date(2026, 8, 31))])

    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
    assert _service(rolled_back_session).close_month(2026, 8, user_id).closed == 1


def test_the_months_flights_reach_the_engine_by_start_then_id(rolled_back_session, user_id, monkeypatch):
    lines = _august_lines(rolled_back_session)
    seen: list[list[tuple[date, int]]] = []
    original = margin_closing_service.price_flights

    def spy(schedules, platform_rates, flights, as_of, opening_positions=None):
        seen.append([(f.flight_start, f.flight_id) for f in flights])
        return original(schedules, platform_rates, flights, as_of, opening_positions)

    monkeypatch.setattr(margin_closing_service, "price_flights", spy)

    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
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
    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)

    MarginClosingService(transaction, today=lambda: SEPTEMBER_FIRST, now=lambda: datetime(2026, 9, 1)).close_month(2026, 8, user_id)

    assert calls[:2] == ["lock 2026-8", "read"]


def test_a_failure_halfway_leaves_no_row(rolled_back_session, user_id, monkeypatch):
    lines = _august_lines(rolled_back_session)
    _schedule(rolled_back_session, _group_of(rolled_back_session, lines[0]), ("0", "1000", "0.15"), ("1000", None, "0.2"))
    insert_ingestion_batch(rolled_back_session)  # so that the header names a batch too
    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
    rolled_back_session.commit()  # the fixtures stay; only the closing may be undone
    original_save = sqlalchemy_margin_repositories.SqlAlchemyAppliedRateRepository.save
    written: list[int] = []

    def failing_save(self, priced, closed_at, closed_by, month_closing_id):
        original_save(self, priced[:1], closed_at, closed_by, month_closing_id)  # the header and one flight ...
        written.append(len(_snapshots(rolled_back_session)))
        raise RuntimeError("forced failure")                                    # ... and then the closing fails

    monkeypatch.setattr(sqlalchemy_margin_repositories.SqlAlchemyAppliedRateRepository, "save", failing_save)

    with pytest.raises(RuntimeError, match="forced failure"):
        _service(rolled_back_session).close_month(2026, 8, user_id)

    assert written == [1]  # something was written before the failure
    assert _rows(rolled_back_session) == []
    assert rolled_back_session.scalar(select(func.count()).select_from(AppliedRateBracketRecord)) == 0
    assert _snapshots(rolled_back_session) == []
    assert _headers(rolled_back_session) == []
    assert rolled_back_session.scalar(select(func.count()).select_from(MonthClosingBatchRecord)) == 0


def test_the_next_closing_starts_from_the_frozen_position_and_does_not_price_frozen_flights_again(rolled_back_session, user_id):
    line_id = insert_campaign_line(rolled_back_session, start_date=date(2026, 7, 1), end_date=date(2026, 8, 31))
    replace_flights(rolled_back_session, line_id, [(date(2026, 7, 1), date(2026, 7, 31)), (date(2026, 8, 1), date(2026, 8, 31))])
    # Each flight delivers its 1,000,000 contracted impressions, so each bills 5,000.00 EUR (committed-billing-and-review).
    batch = insert_ingestion_batch(rolled_back_session)
    insert_delivery(rolled_back_session, line_id, date(2026, 7, 10), 1_000_000, batch)
    insert_delivery(rolled_back_session, line_id, date(2026, 8, 10), 1_000_000, batch)
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
    make_month_closable(rolled_back_session, 2026, 7, user_id, SEPTEMBER_FIRST)
    service.close_month(2026, 7, user_id)
    july = _rows(rolled_back_session)[0]
    july_snapshot = (july.rebate_amount, july.position_before, july.position_after)

    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
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
    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
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

    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
    _service(rolled_back_session).close_month(2026, 8, user_id)

    assert _rows(rolled_back_session)[0].platform_rate == Decimal("1.40")


def test_pending_close_figures_are_the_figures_closing_freezes(rolled_back_session, user_id, monkeypatch):
    """Three flights of one counter, read as a pending-close read would, then closed: the same to the cent.

    They deliver 100,000 to 300,000 of their 1,000,000 contracted, so each bills its delivery, not its contract.
    """
    lines = _august_lines(rolled_back_session, count=3, deliver_the_contract=False)
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
    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)

    MarginClosingService(transaction, today=lambda: SEPTEMBER_FIRST, now=lambda: datetime(2026, 9, 1)).close_month(2026, 8, user_id)

    assert called == [1]  # the closing goes through the same domain function the reads use
    frozen = {row.campaign_line_period_id: row for row in _rows(rolled_back_session)}
    assert len(frozen) == 3
    for item in pending:
        row = frozen[item.facts.flight_id]
        margin_from_frozen = calculate_flight_margin(
            flight_economics(
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
    snapshots = {snapshot.applied_rate_id: snapshot for snapshot in _snapshots(rolled_back_session)}
    assert len(snapshots) == 3
    for item in pending:
        stored = _snapshot_of_record(snapshots[frozen[item.facts.flight_id].id])
        assert stored == snapshot_of(item)
        assert margin_from_snapshot(stored, item.facts.flight_start, item.facts.flight_end) == item.margin


def test_changing_the_system_rate_after_closing_does_not_move_the_frozen_flight(rolled_back_session, user_id):
    _august_lines(rolled_back_session, count=1)
    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
    _service(rolled_back_session).close_month(2026, 8, user_id)
    frozen = _rows(rolled_back_session)[0]
    assert frozen.platform_rate == Decimal("1.000000")

    rolled_back_session.add(PlatformRateSettingRecord(level="system", rate_per_thousand=Decimal("2.50"), created_by=user_id))
    rolled_back_session.flush()
    _service(rolled_back_session, today=date(2026, 9, 30)).close_month(2026, 8, user_id)

    rolled_back_session.refresh(frozen)
    assert frozen.platform_rate == Decimal("1.000000")
    assert len(_rows(rolled_back_session)) == 1


def test_closing_a_dooh_month_freezes_a_platform_cost_on_impressions_and_changes_none_of_its_delivery(
    rolled_back_session: Session, user_id: int
) -> None:
    line_id = insert_campaign_line(rolled_back_session, delivery_metric="ots")
    insert_delivery(
        rolled_back_session, line_id, date(2026, 8, 10), 12_000, insert_ingestion_batch(rolled_back_session),
        ots=Decimal("280000.5000"),
    )

    def read() -> FlightMargin:
        service = MarginQueryService(
            SqlAlchemyMarginReadRepository(rolled_back_session), SqlAlchemyRebateScheduleRepository(rolled_back_session),
            SqlAlchemyPlatformRateRepository(rolled_back_session), SqlAlchemyAppliedRateRepository(rolled_back_session),
            today=lambda: SEPTEMBER_FIRST,
        )
        (campaign,) = service.get_margin().campaigns
        (line,) = campaign.lines
        (flight,) = line.flights
        return flight.margin

    before = read()
    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
    _service(rolled_back_session).close_month(2026, 8, user_id)
    after = read()

    assert before.platform_cost == after.platform_cost == Decimal("12.00")  # 12,000 impressions, not 280.00 €
    for margin in (before, after):
        assert (margin.delivered, margin.delivered_impressions, margin.delivery_metric) == (
            Decimal("280000.5000"), 12_000, "ots",
        )
    assert len(_rows(rolled_back_session)) == 1


# ---------------------------------------------------------------- target flights: the freeze and the block (decision 9)
#
# November 2026, closed on 1 December (as_of 30 November). One campaign on the Deal counter of its group, with a flat
# 10 % schedule: line 1 is committed (1,000,000 at 5.00 €, a sale of 5,000.00 €), line 2 is the worked example, a
# target line on Equativ mapped to the package 900000001, whose 1,100,000 served at 5.00 € are a gross of 5,500.00 €
# and whose reported revenue is 4,400.00 €.

DECEMBER_FIRST = date(2026, 12, 1)
NOVEMBER = (date(2026, 11, 1), date(2026, 11, 30))
PACKAGE = "900000001"


class _November:
    def __init__(self, session: Session, engine: Engine) -> None:
        self.session = session
        self.engine = engine
        self.equativ = insert_other_dsp(session, "Equativ")
        self.committed = insert_campaign_line(session, "Deal campaign", *NOVEMBER)
        replace_flights(session, self.committed, [NOVEMBER])
        self.target = add_line_to_campaign(session, self.committed, 2)
        deal = session.scalars(select(ChannelRecord).where(ChannelRecord.name == "Deal")).first()
        if deal is None:
            deal = ChannelRecord(name="Deal", delivery_metric="impressions")
            session.add(deal)
            session.flush()
        self.deal_channel = deal.id
        session.execute(
            update(CampaignLineRecord).where(CampaignLineRecord.id.in_([self.committed, self.target]))
            .values(channel_id=deal.id)
        )
        session.execute(
            update(CampaignLineRecord).where(CampaignLineRecord.id == self.target)
            .values(volume_commitment="target", dsp_id=self.equativ)
        )
        insert_mapping(session, self.target, self.equativ, PACKAGE, PACKAGE, validated_at=datetime(2026, 11, 1, 10, 0))
        _schedule(session, _group_of(session, self.committed), ("0", None, "0.10"))
        session.commit()

    def ingest(self, start: str, end: str, *rows: dict[str, str]) -> None:
        """Run the nightly command for Equativ over a custom range, against the synthetic Equativ.

        The command closes the session it is given, so what the test added before is committed first.
        """
        self.session.commit()
        client = EquativDeliveryClient(
            "synthetic-equativ-client-id", "synthetic-equativ-client-secret", FakeEquativ(rows=list(rows)).client(),
            sleep=lambda _: None, monotonic=lambda: 0.0,
        )
        code = run_ingestion(
            ["--dsp", "Equativ", "--from", start, "--to", end], out=lambda _: None,
            engine=self.engine, session_factory=lambda: self.session, client=client,
            now=lambda: datetime(2026, 12, 1, 7, 0, tzinfo=UTC),
        )
        assert code == 0

    def ingest_the_month(self) -> None:
        self.ingest(
            "2026-11-01", "2026-11-30",
            package_row(day="2026-11-10T00:00:00", impressions="600000", spend="3000.00", revenue="2400.00"),
            package_row(day="2026-11-30T00:00:00", impressions="500000", spend="2500.00", revenue="2000.00"),
        )

    def row_of(self, line_id: int) -> AppliedRateRecord:
        return self.session.scalars(
            select(AppliedRateRecord).join(
                CampaignLinePeriodRecord, CampaignLinePeriodRecord.id == AppliedRateRecord.campaign_line_period_id
            ).where(CampaignLinePeriodRecord.campaign_line_id == line_id)
        ).one()

    def target_report(self) -> FlightReport:
        (flight,) = _flight_reports(_read_margin(self.session, DECEMBER_FIRST), self.target)
        return flight

    def target_margin(self) -> FlightMargin:
        return self.target_report().margin


@pytest.fixture
def november(rolled_back_session: Session, test_engine: Engine) -> _November:
    return _November(rolled_back_session, test_engine)


def _batch(session: Session, dsp_id: int, status: str, window: tuple[date, date]) -> None:
    session.add(IngestionBatchRecord(
        dsp_id=dsp_id, route="api", source_file=None, started_at=datetime(2026, 12, 1, 6, 15),
        finished_at=datetime(2026, 12, 1, 6, 20), status=status, row_count=0, window_start=window[0],
        window_end=window[1],
    ))
    session.commit()


def test_closing_the_worked_examples_month_freezes_its_revenue_and_its_gross_and_the_billing_of_a_committed_row(
    november: _November, user_id: int
) -> None:
    november.ingest_the_month()
    # The committed flight delivers its 1,000,000 contracted impressions, so it bills its 5,000.00 € contracted sale
    # (committed-billing-and-review) and the Deal counter stands there before the target flight.
    insert_delivery(november.session, november.committed, date(2026, 11, 10), 1_000_000,
                    insert_ingestion_batch(november.session))

    make_month_closable(november.session, 2026, 11, user_id, DECEMBER_FIRST)
    result = _service(november.session, today=DECEMBER_FIRST).close_month(2026, 11, user_id)

    assert (result.closed, result.already_closed) == (2, 0)
    target, committed = november.row_of(november.target), november.row_of(november.committed)
    assert (target.revenue_amount, target.rebate_base_amount) == (Decimal("4400.00"), Decimal("5500.00"))
    assert target.rebate_amount == Decimal("550.00")  # 10 % of the gross, not of the 4,400.00 reported
    # The Deal counter advances by the gross: from the committed flight's 5,000.00 to 10,500.00.
    assert target.counter_channel_id == committed.counter_channel_id == november.deal_channel
    assert (target.position_before, target.position_after) == (Decimal("5000.00"), Decimal("10500.00"))
    # A committed row holds its billing as both (committed-billing-and-review).
    assert (committed.revenue_amount, committed.rebate_base_amount) == (Decimal("5000.00"), Decimal("5000.00"))
    assert (committed.position_before, committed.position_after) == (Decimal(0), Decimal("5000.00"))


def test_a_restatement_after_closing_moves_no_figure_of_the_closed_month_and_flags_the_change(
    november: _November, user_id: int
) -> None:
    november.ingest_the_month()
    make_month_closable(november.session, 2026, 11, user_id, DECEMBER_FIRST)
    _service(november.session, today=DECEMBER_FIRST).close_month(2026, 11, user_id)
    closed = november.target_report()

    # Equativ restates 30 November: more impressions, more reported revenue and more spend. The run replaces the day.
    november.ingest(
        "2026-11-30", "2026-11-30",
        package_row(day="2026-11-30T00:00:00", impressions="700000", spend="3500.00", revenue="2600.00"),
    )
    restated = november.target_report()

    assert (closed.margin.revenue, closed.margin.gross_revenue, closed.margin.rebate) == (
        Decimal("4400.00"), Decimal("5500.00"), Decimal("550.00"),
    )
    # The closed flight is read from its snapshot: nothing moves, not even the platform cost or the gross flag.
    assert replace(restated.margin, delivery_changed=False) == closed.margin
    assert (restated.margin.platform_cost, restated.margin.gross_differs_from_buyer_spend) == (Decimal("1100.00"), False)
    assert (closed.margin.delivery_changed, restated.margin.delivery_changed) == (False, True)
    # 1,300,000 served, 5,000.00 € reported and 6,500.00 € spent now: 5,000.00 − 0.00 − 550.00 − 1,300.00 = 3,150.00 €.
    assert restated.delivery_change == ClosedDeliveryCheck(
        delivered_difference=Decimal("200000.0000"), delivered_impressions_difference=200_000,
        media_cost_difference=Decimal("0.00"), reported_revenue_difference=Decimal("600.00"),
        buyer_spend_difference=Decimal("1000.00"), current_margin=Decimal("3150.00"),
        margin_difference=Decimal("400.00"), changed=True,
    )


def test_closing_a_month_with_target_flights_twice_neither_adds_nor_changes_a_row(
    november: _November, user_id: int
) -> None:
    november.ingest_the_month()
    make_month_closable(november.session, 2026, 11, user_id, DECEMBER_FIRST)
    _service(november.session, today=DECEMBER_FIRST).close_month(2026, 11, user_id)
    before = [(r.id, r.rebate_amount, r.revenue_amount, r.rebate_base_amount, r.position_after)
              for r in _rows(november.session)]

    second = _service(november.session, today=date(2026, 12, 20)).close_month(2026, 11, user_id)

    assert (second.closed, second.already_closed) == (0, 2)
    assert [(r.id, r.rebate_amount, r.revenue_amount, r.rebate_base_amount, r.position_after)
            for r in _rows(november.session)] == before


def test_a_month_with_a_target_flight_whose_dsp_has_not_loaded_its_last_day_is_not_closed(
    november: _November, user_id: int
) -> None:
    _batch(november.session, seeded_dsp_id(november.session), "succeeded", (date(2026, 11, 30), date(2026, 11, 30)))
    _batch(november.session, november.equativ, "succeeded", (date(2026, 11, 23), date(2026, 11, 29)))

    with pytest.raises(MonthDeliveryNotLoadedError) as blocked:
        _service(november.session, today=DECEMBER_FIRST).close_month(2026, 11, user_id)

    assert (blocked.value.year, blocked.value.month, blocked.value.dsp_name) == (2026, 11, "Equativ")
    assert _rows(november.session) == []


def test_a_succeeded_batch_of_its_dsp_whose_window_includes_the_last_day_unblocks_the_month(
    november: _November, user_id: int
) -> None:
    _batch(november.session, seeded_dsp_id(november.session), "succeeded", (date(2026, 11, 30), date(2026, 11, 30)))
    _batch(november.session, november.equativ, "succeeded", (date(2026, 11, 23), date(2026, 11, 29)))
    _batch(november.session, november.equativ, "succeeded", (date(2026, 11, 24), date(2026, 11, 30)))

    make_month_closable(november.session, 2026, 11, user_id, DECEMBER_FIRST, load_last_day=False)
    result = _service(november.session, today=DECEMBER_FIRST).close_month(2026, 11, user_id)

    assert result.closed == 2


def test_a_failed_batch_of_its_dsp_or_a_succeeded_batch_of_another_dsp_does_not_unblock(
    november: _November, user_id: int
) -> None:
    adform = insert_other_dsp(november.session, "Adform")
    _batch(november.session, seeded_dsp_id(november.session), "succeeded", (date(2026, 11, 30), date(2026, 11, 30)))
    _batch(november.session, november.equativ, "failed", (date(2026, 11, 24), date(2026, 11, 30)))
    _batch(november.session, adform, "succeeded", (date(2026, 11, 24), date(2026, 11, 30)))

    with pytest.raises(MonthDeliveryNotLoadedError) as blocked:
        _service(november.session, today=DECEMBER_FIRST).close_month(2026, 11, user_id)
    assert blocked.value.dsp_name == "Equativ"
    assert _rows(november.session) == []


def test_a_month_of_committed_adform_lines_only_waits_for_adform_to_load_its_last_day(
    rolled_back_session: Session, user_id: int
) -> None:
    # committed-billing-and-review: a committed flight bills its delivery, so its month waits for its DSP as well.
    adform = insert_other_dsp(rolled_back_session, "Adform")
    line = insert_campaign_line(rolled_back_session, "Adform only", *NOVEMBER, dsp_id=adform)
    replace_flights(rolled_back_session, line, [NOVEMBER])
    _batch(rolled_back_session, adform, "succeeded", (date(2026, 11, 23), date(2026, 11, 29)))

    with pytest.raises(MonthDeliveryNotLoadedError) as blocked:
        _service(rolled_back_session, today=DECEMBER_FIRST).close_month(2026, 11, user_id)

    assert (blocked.value.year, blocked.value.month, blocked.value.dsp_name) == (2026, 11, "Adform")
    assert _rows(rolled_back_session) == []
    _batch(rolled_back_session, adform, "succeeded", (date(2026, 11, 24), date(2026, 11, 30)))
    make_month_closable(rolled_back_session, 2026, 11, user_id, DECEMBER_FIRST, load_last_day=False)
    assert _service(rolled_back_session, today=DECEMBER_FIRST).close_month(2026, 11, user_id).closed == 1


def test_an_earlier_open_month_is_still_reported_before_a_month_not_loaded(november: _November, user_id: int) -> None:
    october = insert_campaign_line(november.session, "October open", date(2026, 10, 1), date(2026, 10, 31))
    replace_flights(november.session, october, [(date(2026, 10, 1), date(2026, 10, 31))])

    with pytest.raises(PreviousMonthOpenError) as blocked:
        _service(november.session, today=DECEMBER_FIRST).close_month(2026, 11, user_id)

    assert (blocked.value.year, blocked.value.month) == (2026, 10)
    assert _rows(november.session) == []



# --- A closed month is read from its snapshots; the delivery stored afterwards only raises the warning ---------------
#
# The committed Adform flight of finance/rebate-accrual: November, 1,000,000 contracted at 5.00 €, a flat rebate of
# 25 % and a platform rate of 1.00 €. Closed on 1 December with 700,000 delivered impressions and 1,200.00 € of media
# cost: 5,000.00 − 1,200.00 − 1,250.00 − 700.00 = 1,850.00 €. The run of 3 December restates 28 November with 500,000
# more impressions and 1,800.00 € more media cost: its current margin would be 5,000.00 − 3,000.00 − 1,250.00 −
# 1,200.00 = −450.00 €.

ADFORM_KEY = ExternalLineKey("1001", "2001")


def _adform_november(session: Session) -> int:
    line_id = insert_campaign_line(session, "Adform committed", *NOVEMBER)
    replace_flights(session, line_id, [NOVEMBER])
    insert_mapping(session, line_id, seeded_dsp_id(session), "1001", "2001")
    _schedule(session, _group_of(session, line_id), ("0", None, "0.25"))
    return line_id


def _adform_run(session: Session, today: date, rows: list[DspDeliveryRow], window: DeliveryDateRange | None = None) -> None:
    service = DeliveryIngestionService(
        InMemoryDspDeliveryClient(rows), lambda: SqlAlchemyUnitOfWork(lambda: session),
        lambda: datetime.combine(today, datetime.min.time()).replace(hour=2),
    )
    result = service.run(seeded_dsp_id(session), today, window=window)
    assert result.stored_row_count == len(rows)


def _closed_adform_november(session: Session, user_id: int) -> int:
    line_id = _adform_november(session)
    _adform_run(session, DECEMBER_FIRST, [
        dsp_row(date(2026, 11, 10), ADFORM_KEY, impressions=400_000, media_cost=Decimal("600.000000")),
        dsp_row(date(2026, 11, 28), ADFORM_KEY, impressions=300_000, media_cost=Decimal("600.000000")),
    ], window=DeliveryDateRange(date(2026, 11, 1), date(2026, 11, 30)))
    make_month_closable(session, 2026, 11, user_id, DECEMBER_FIRST)
    result = _service(session, today=DECEMBER_FIRST).close_month(2026, 11, user_id)
    assert result.closed == 1
    return line_id


def test_the_committed_example_keeps_its_closed_margin_after_the_restatement_and_flags_it(
    rolled_back_session: Session, user_id: int
) -> None:
    line_id = _closed_adform_november(rolled_back_session, user_id)
    (before,) = _flight_reports(_read_margin(rolled_back_session, date(2026, 12, 2)), line_id)

    # The nightly run of 3 December replaces its window, 26 November to 2 December, through the ingestion service.
    _adform_run(rolled_back_session, date(2026, 12, 3), [
        dsp_row(date(2026, 11, 28), ADFORM_KEY, impressions=800_000, media_cost=Decimal("2400.000000")),
    ])
    report = _read_margin(rolled_back_session, date(2026, 12, 4))
    (after,) = _flight_reports(report, line_id)

    # It bills the 700,000 it delivered, 3,500.00 €, with a 25 % rebate of 875.00 € (committed-billing-and-review).
    assert (before.margin.margin, before.margin.delivery_changed) == (Decimal("725.00"), False)
    assert after.state is FlightState.CLOSED
    assert (after.margin.revenue, after.margin.media_cost, after.margin.platform_cost, after.margin.margin) == (
        Decimal("3500.00"), Decimal("1200.00"), Decimal("700.00"), Decimal("725.00"),
    )
    assert after.margin.delivered_impressions == 700_000
    assert replace(after.margin, delivery_changed=False) == before.margin
    assert after.margin.delivery_changed is True
    assert after.delivery_change == ClosedDeliveryCheck(
        delivered_difference=Decimal("500000.0000"), delivered_impressions_difference=500_000,
        media_cost_difference=Decimal("1800.00"), reported_revenue_difference=None, buyer_spend_difference=None,
        # The check compares with the current billing: 1,200,000 delivered bills the cap, 5,000.00 €, so
        # 5,000.00 - 3,000.00 - 875.00 - 1,200.00 = -75.00 €.
        current_margin=Decimal("-75.00"), margin_difference=Decimal("-800.00"), changed=True,
        billable_difference=Decimal("300000.0000"), billing_difference=Decimal("1500.00"),
    )
    (campaign,) = [c for c in report.campaigns if any(line.campaign_line_id == line_id for line in c.lines)]
    for totals in (campaign.lines[0].totals, campaign.totals):
        assert (totals.margin, totals.media_cost, totals.delivery_changed_count) == (
            Decimal("725.00"), Decimal("1200.00"), 1,
        )
    assert report.totals.delivery_changed_count == 1


def test_a_closed_flight_read_with_no_change_to_its_delivery_equals_its_pending_close_read(
    rolled_back_session: Session, user_id: int
) -> None:
    line_id = _adform_november(rolled_back_session)
    _adform_run(rolled_back_session, DECEMBER_FIRST, [
        dsp_row(date(2026, 11, 28), ADFORM_KEY, impressions=700_000, media_cost=Decimal("1200.004")),
    ], window=DeliveryDateRange(date(2026, 11, 1), date(2026, 11, 30)))
    (pending,) = _flight_reports(_read_margin(rolled_back_session, DECEMBER_FIRST), line_id)

    make_month_closable(rolled_back_session, 2026, 11, user_id, DECEMBER_FIRST)
    _service(rolled_back_session, today=DECEMBER_FIRST).close_month(2026, 11, user_id)
    (closed,) = _flight_reports(_read_margin(rolled_back_session, DECEMBER_FIRST), line_id)

    assert pending.state is FlightState.PENDING_CLOSE and closed.state is FlightState.CLOSED
    assert closed.margin == replace(pending.margin, provisional=False)
    assert closed.delivery_change is not None and closed.delivery_change.changed is False
    assert closed.delivery_change.current_margin == closed.margin.margin == Decimal("725.00")


def test_unlinking_a_line_with_a_closed_flight_keeps_its_closed_figures(rolled_back_session: Session, user_id: int) -> None:
    line_id = _closed_adform_november(rolled_back_session, user_id)
    (before,) = _flight_reports(_read_margin(rolled_back_session, date(2026, 12, 2)), line_id)

    removed = LineMappingRemovalService(SqlAlchemyLineMappingRemovalRepository(rolled_back_session)).unlink(line_id)
    (after,) = _flight_reports(_read_margin(rolled_back_session, date(2026, 12, 2)), line_id)

    assert removed == 2
    assert replace(after.margin, delivery_changed=False) == before.margin
    assert after.margin.delivery_changed is True
    assert after.delivery_change is not None
    # With its delivery gone it would bill nothing: 0.00 - 0.00 - 875.00 - 0.00 = -875.00 €.
    assert (after.delivery_change.delivered_impressions_difference, after.delivery_change.current_margin) == (
        -700_000, Decimal("-875.00"),
    )
    assert (after.delivery_change.billable_difference, after.delivery_change.billing_difference) == (
        Decimal("-700000.0000"), Decimal("-3500.00"),
    )


def test_a_change_of_the_channel_s_metric_after_closing_does_not_move_a_closed_flight(
    rolled_back_session: Session, user_id: int
) -> None:
    line_id = insert_campaign_line(rolled_back_session, "DOOH", *NOVEMBER, delivery_metric="ots")
    replace_flights(rolled_back_session, line_id, [NOVEMBER])
    insert_delivery(rolled_back_session, line_id, date(2026, 11, 10), 12_000, insert_ingestion_batch(rolled_back_session),
                    ots=Decimal("280000.5000"))
    make_month_closable(rolled_back_session, 2026, 11, user_id, DECEMBER_FIRST)
    _service(rolled_back_session, today=DECEMBER_FIRST).close_month(2026, 11, user_id)
    (before,) = _flight_reports(_read_margin(rolled_back_session, DECEMBER_FIRST), line_id)
    channel_id = rolled_back_session.get(CampaignLineRecord, line_id).channel_id  # type: ignore[union-attr]

    rolled_back_session.execute(
        update(ChannelRecord).where(ChannelRecord.id == channel_id).values(delivery_metric="impressions")
    )
    (after,) = _flight_reports(_read_margin(rolled_back_session, DECEMBER_FIRST), line_id)

    assert after.margin == before.margin
    assert (after.margin.delivery_metric, after.margin.contracted_impressions, after.margin.delivered) == (
        "ots", 1_000_000, Decimal("280000.5000"),
    )
    assert after.delivery_change is not None and after.delivery_change.changed is False


def test_a_running_or_pending_close_flight_carries_no_check(rolled_back_session: Session) -> None:
    running = insert_campaign_line(rolled_back_session, "Running", date(2026, 11, 1), date(2026, 12, 31))
    replace_flights(rolled_back_session, running, [(date(2026, 12, 1), date(2026, 12, 31))])
    pending = insert_campaign_line(rolled_back_session, "Pending close", *NOVEMBER)
    replace_flights(rolled_back_session, pending, [NOVEMBER])

    report = _read_margin(rolled_back_session, date(2026, 12, 10))

    for line_id, state in ((running, FlightState.RUNNING), (pending, FlightState.PENDING_CLOSE)):
        (flight,) = _flight_reports(report, line_id)
        assert flight.state is state
        assert (flight.delivery_change, flight.margin.delivery_changed) == (None, False)
    assert report.totals.delivery_changed_count == 0


# --- The closing waits for the review (committed-billing-and-review) -------------------------------------------------


def _two_august_campaigns(session: Session) -> tuple[int, int]:
    """Two August campaigns of one line each, both delivered and loaded up to 31 August: A and B."""
    batch = insert_ingestion_batch(session)
    first = insert_campaign_line(session, "Campaign A")
    second = insert_campaign_line(session, "Campaign B")
    for line_id in (first, second):
        insert_delivery(session, line_id, date(2026, 8, 10), 700_000, batch)
    load_months_last_day(session, 2026, 8)
    return first, second


def _campaign_of(session: Session, line_id: int) -> int:
    line = session.get(CampaignLineRecord, line_id)
    assert line is not None
    return line.campaign_id


def test_a_month_with_a_running_flight_is_refused_naming_its_campaign_in_progress(
    rolled_back_session: Session, user_id: int
) -> None:
    line_id = insert_campaign_line(rolled_back_session, "Running campaign")
    load_months_last_day(rolled_back_session, 2026, 8)

    with pytest.raises(MonthNotReviewedError) as refused:
        _service(rolled_back_session, today=date(2026, 8, 31)).close_month(2026, 8, user_id)

    assert (refused.value.year, refused.value.month) == (2026, 8)
    assert refused.value.campaigns == (("Running campaign", ReviewState.IN_PROGRESS),)
    assert "2026-08" in str(refused.value) and "Running campaign" in str(refused.value)
    assert (_rows(rolled_back_session), _headers(rolled_back_session), _snapshots(rolled_back_session)) == ([], [], [])
    assert line_id


def test_a_month_with_a_campaign_pending_review_is_refused_naming_it_and_closes_once_it_is_reviewed(
    rolled_back_session: Session, user_id: int
) -> None:
    first, second = _two_august_campaigns(rolled_back_session)
    reviews = MonthlyReviewService(
        SqlAlchemyMonthlyReviewTransaction(rolled_back_session), today=lambda: SEPTEMBER_FIRST,
        now=lambda: datetime(2026, 9, 1, 8, 0),
    )
    reviews.review(_campaign_of(rolled_back_session, first), 2026, 8, user_id)

    with pytest.raises(MonthNotReviewedError) as refused:
        _service(rolled_back_session).close_month(2026, 8, user_id)

    assert refused.value.campaigns == (("Campaign B", ReviewState.PENDING_REVIEW),)
    assert (_rows(rolled_back_session), _headers(rolled_back_session)) == ([], [])
    reviews.review(_campaign_of(rolled_back_session, second), 2026, 8, user_id)
    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
    assert _service(rolled_back_session).close_month(2026, 8, user_id).closed == 2


def test_the_refusal_names_every_blocking_campaign_with_its_state_and_not_a_reviewed_one(
    rolled_back_session: Session, user_id: int
) -> None:
    # As of 30 August: A ended on the 15th and is reviewed, B ended on the 20th and is pending, C runs to the 31st.
    today = date(2026, 8, 31)
    lines = {name: insert_campaign_line(rolled_back_session, name) for name in ("Campaign C", "Campaign B", "Campaign A")}
    for name, last_day in (("Campaign A", 15), ("Campaign B", 20), ("Campaign C", 31)):
        rolled_back_session.execute(
            update(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.campaign_line_id == lines[name])
            .values(flight_end=date(2026, 8, last_day))
        )
    load_months_last_day(rolled_back_session, 2026, 8)
    MonthlyReviewService(
        SqlAlchemyMonthlyReviewTransaction(rolled_back_session), today=lambda: today, now=lambda: datetime(2026, 8, 31, 8, 0),
    ).review(_campaign_of(rolled_back_session, lines["Campaign A"]), 2026, 8, user_id)

    with pytest.raises(MonthNotReviewedError) as refused:
        _service(rolled_back_session, today=today).close_month(2026, 8, user_id)

    assert refused.value.campaigns == (
        ("Campaign B", ReviewState.PENDING_REVIEW), ("Campaign C", ReviewState.IN_PROGRESS),
    )
    assert "Campaign A" not in str(refused.value)
    assert _rows(rolled_back_session) == []


def test_a_closed_campaign_does_not_block_a_later_closing_but_a_late_one_does_until_it_is_reviewed(
    rolled_back_session: Session, user_id: int
) -> None:
    _two_august_campaigns(rolled_back_session)
    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
    assert _service(rolled_back_session).close_month(2026, 8, user_id).closed == 2
    late = insert_campaign_line(rolled_back_session, "Late campaign")
    rolled_back_session.commit()  # the refused closing rolls back what was only flushed

    with pytest.raises(MonthNotReviewedError) as refused:
        _service(rolled_back_session, today=date(2026, 9, 20)).close_month(2026, 8, user_id)

    assert refused.value.campaigns == (("Late campaign", ReviewState.PENDING_REVIEW),)
    review_month(rolled_back_session, 2026, 8, user_id, date(2026, 9, 20))
    assert _service(rolled_back_session, today=date(2026, 9, 20)).close_month(2026, 8, user_id).closed == 1
    assert late


def test_a_month_not_loaded_is_reported_before_a_month_not_reviewed(rolled_back_session: Session, user_id: int) -> None:
    line_id = insert_campaign_line(rolled_back_session, "Pending and not loaded")
    insert_delivery(rolled_back_session, line_id, date(2026, 8, 10), 700_000, insert_ingestion_batch(rolled_back_session))
    rolled_back_session.commit()  # the refused closing rolls back what was only flushed

    with pytest.raises(MonthDeliveryNotLoadedError):
        _service(rolled_back_session).close_month(2026, 8, user_id)
    load_months_last_day(rolled_back_session, 2026, 8)
    rolled_back_session.commit()
    with pytest.raises(MonthNotReviewedError):
        _service(rolled_back_session).close_month(2026, 8, user_id)


def test_a_campaign_in_progress_is_reported_before_a_month_not_loaded(rolled_back_session: Session, user_id: int) -> None:
    # As of 30 August: A ended on the 15th and its DSP has not loaded 31 August, which it cannot while C still runs.
    lines = {name: insert_campaign_line(rolled_back_session, name) for name in ("Campaign A", "Campaign C")}
    rolled_back_session.execute(
        update(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.campaign_line_id == lines["Campaign A"])
        .values(flight_end=date(2026, 8, 15))
    )

    with pytest.raises(MonthNotReviewedError) as refused:
        _service(rolled_back_session, today=date(2026, 8, 31)).close_month(2026, 8, user_id)

    assert refused.value.campaigns == (
        ("Campaign A", ReviewState.PENDING_REVIEW), ("Campaign C", ReviewState.IN_PROGRESS),
    )


def test_an_earlier_open_month_is_reported_before_a_month_not_reviewed(rolled_back_session: Session, user_id: int) -> None:
    line_id = insert_campaign_line(rolled_back_session, start_date=date(2026, 7, 1), end_date=date(2026, 8, 31))
    replace_flights(rolled_back_session, line_id, [(date(2026, 7, 1), date(2026, 7, 31)), (date(2026, 8, 1), date(2026, 8, 31))])
    load_months_last_day(rolled_back_session, 2026, 8)

    with pytest.raises(PreviousMonthOpenError):
        _service(rolled_back_session).close_month(2026, 8, user_id)


def test_a_reviewed_month_freezes_the_billing_of_a_committed_flight(rolled_back_session: Session, user_id: int) -> None:
    # 700,000 of 1,000,000 contracted at 5.00 € with a 25 % schedule: it bills 3,500.00 € and accrues 875.00 €.
    (line_id,) = _august_lines(rolled_back_session, count=1, deliver_the_contract=False)
    insert_delivery(rolled_back_session, line_id, date(2026, 8, 10), 700_000, insert_ingestion_batch(rolled_back_session))
    _schedule(rolled_back_session, _group_of(rolled_back_session, line_id), ("0", None, "0.25"))
    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)

    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
    _service(rolled_back_session).close_month(2026, 8, user_id)

    (row,) = _rows(rolled_back_session)
    assert (row.revenue_amount, row.rebate_base_amount, row.rebate_amount) == (
        Decimal("3500.00"), Decimal("3500.00"), Decimal("875.00"),
    )
    # The counter advances by the billing, not by the 5,000.00 € contracted.
    assert (row.position_before, row.position_after) == (Decimal(0), Decimal("3500.00"))
    (snapshot,) = _snapshots(rolled_back_session)
    assert (snapshot.revenue, snapshot.contracted_revenue) == (Decimal("3500.00"), Decimal("5000.00"))
    assert (snapshot.billing_basis, snapshot.billable, snapshot.carryover, snapshot.carryover_billable,
            snapshot.billing_adjustment_id) == ("minimum", Decimal("700000.0000"), 0, False, None)


def test_an_adjusted_flight_freezes_its_adjustment_in_force(rolled_back_session: Session, user_id: int) -> None:
    (line_id,) = _august_lines(rolled_back_session, count=1, deliver_the_contract=False)
    insert_delivery(rolled_back_session, line_id, date(2026, 8, 10), 700_000, insert_ingestion_batch(rolled_back_session))
    (flight_id,) = [f.id for f in rolled_back_session.scalars(
        select(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.campaign_line_id == line_id))]
    adjustments = BillingAdjustmentService(
        SqlAlchemyBillingAdjustmentTransaction(rolled_back_session), today=lambda: SEPTEMBER_FIRST,
        now=lambda: datetime(2026, 9, 1, 8, 0),
    )
    adjustments.adjust(flight_id, BillingBasis.DELIVERED, None, "Billed as served", user_id)
    latest = adjustments.adjust(flight_id, BillingBasis.CONTRACTED, None, "Agreed with the agency", user_id)
    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)

    make_month_closable(rolled_back_session, 2026, 8, user_id, SEPTEMBER_FIRST)
    _service(rolled_back_session).close_month(2026, 8, user_id)

    (snapshot,) = _snapshots(rolled_back_session)
    assert (snapshot.billing_basis, snapshot.billable, snapshot.billing_adjustment_id, snapshot.revenue) == (
        "contracted", Decimal("1000000.0000"), latest.entry.entry_id, Decimal("5000.00"),
    )
    (row,) = _rows(rolled_back_session)
    assert (row.revenue_amount, row.rebate_base_amount) == (Decimal("5000.00"), Decimal("5000.00"))
