"""The ingestion service through PostgreSQL: the same window twice, and a resolved pair that delivers again."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.application.services.delivery_ingestion_service import DeliveryIngestionService
from app.domain.entities.ingestion_batch import IngestionRoute
from app.domain.value_objects.delivery import ExternalLineKey
from app.infrastructure.persistence.models.delivery import (
    DailyDeliveryRecord,
    IngestionBatchRecord,
    IngestionExceptionDeliveryRecord,
    IngestionExceptionRecord,
)
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.fixtures.delivery_data import (
    insert_campaign_line,
    insert_ingestion_batch,
    insert_mapping,
    insert_user,
    replace_flights,
    seeded_dsp_id,
)
from tests.fixtures.delivery_rows import dsp_row
from tests.fixtures.dsp_delivery_client import InMemoryDspDeliveryClient

TODAY = date(2026, 8, 10)
D5, D6 = date(2026, 8, 5), date(2026, 8, 6)
MAPPED = ExternalLineKey("1001", "2001")
STRANGER = ExternalLineKey("9", "9")


class _Setup:
    def __init__(self, session, rows):
        self.session = session
        self.dsp_id = seeded_dsp_id(session)
        self.line_id = insert_campaign_line(session)
        insert_mapping(session, self.line_id, self.dsp_id, "1001", "2001")
        self.client = InMemoryDspDeliveryClient(rows)
        self.service = DeliveryIngestionService(
            self.client, lambda: SqlAlchemyUnitOfWork(lambda: session), lambda: datetime(2026, 8, 10, 2, 0))

    def run(self, route: IngestionRoute = IngestionRoute.API):
        return self.service.run(self.dsp_id, TODAY, route=route)

    def count(self, record) -> int:
        return self.session.scalar(select(func.count()).select_from(record))


@pytest.fixture
def setup(rolled_back_session):
    return _Setup(rolled_back_session, [
        dsp_row(D5, MAPPED, impressions=700), dsp_row(D5, STRANGER, impressions=40), dsp_row(D6, STRANGER, impressions=50),
        dsp_row(D5, ExternalLineKey("8", "8"), impressions=0, media_cost=Decimal("0")),
    ])


def test_matched_delivery_is_stored_and_unmatched_delivery_is_kept_as_an_exception(setup):
    result = setup.run()

    assert setup.count(DailyDeliveryRecord) == 1
    assert setup.count(IngestionExceptionRecord) == 1
    assert setup.count(IngestionExceptionDeliveryRecord) == 2
    assert result.zero_unmatched_row_count == 1


def test_the_batch_counts_the_rows_it_read(setup):
    result = setup.run()

    batch = setup.session.get(IngestionBatchRecord, result.batch_id)
    assert (batch.status, batch.row_count, batch.zero_unmatched_row_count) == ("succeeded", 4, 1)


def test_running_the_same_window_twice_creates_no_second_exception_and_no_duplicate_days(setup):
    setup.run()
    setup.run()

    assert setup.count(IngestionExceptionRecord) == 1
    assert setup.count(IngestionExceptionDeliveryRecord) == 2
    assert setup.count(DailyDeliveryRecord) == 1


def test_the_upload_route_creates_the_same_exception(setup):
    setup.run(route=IngestionRoute.UPLOAD)

    assert setup.count(IngestionExceptionRecord) == 1


def test_a_resolved_pair_that_delivers_again_is_not_reopened_and_its_new_delivery_is_registered(setup):
    setup.run()
    exception = setup.session.scalars(select(IngestionExceptionRecord)).one()
    exception.status, exception.resolved_at, exception.resolved_by = (
        "resolved", datetime(2026, 8, 9, 9, 0), insert_user(setup.session))
    setup.session.flush()
    setup.client._rows = [dsp_row(D5, STRANGER, impressions=77), dsp_row(date(2026, 8, 7), STRANGER, impressions=5)]

    setup.run()

    setup.session.expire_all()
    exception = setup.session.scalars(select(IngestionExceptionRecord)).one()
    retained = {r.delivery_date: r.impressions for r in setup.session.scalars(select(IngestionExceptionDeliveryRecord))}
    assert exception.status == "resolved"
    assert retained == {D5: 77, date(2026, 8, 7): 5}
    assert setup.count(IngestionExceptionRecord) == 1


def test_the_span_follows_the_retained_dates(setup):
    setup.run()

    exception = setup.session.scalars(select(IngestionExceptionRecord)).one()
    assert (exception.first_date, exception.last_date) == (D5, D6)


def test_absence_is_detected_once_per_line_and_period_through_postgres(rolled_back_session):
    dsp_id = seeded_dsp_id(rolled_back_session)
    line = insert_campaign_line(rolled_back_session, "Absent line", date(2026, 7, 1), date(2026, 8, 7))
    insert_mapping(rolled_back_session, line, dsp_id, validated_at=datetime(2026, 7, 20, 9, 0))
    batch_id = insert_ingestion_batch(rolled_back_session)
    service = DeliveryIngestionService(
        InMemoryDspDeliveryClient([]), lambda: SqlAlchemyUnitOfWork(lambda: rolled_back_session),
        lambda: datetime(2026, 8, 10, 2, 0))

    first = service.detect_missing_delivery(dsp_id, TODAY, batch_id)
    second = service.detect_missing_delivery(dsp_id, TODAY, batch_id)

    exception = rolled_back_session.scalars(select(IngestionExceptionRecord)).one()
    assert (first, second) == (1, 0)
    assert (exception.exception_type, exception.status, exception.campaign_line_id) == (
        "missing_delivery", "open", line)


def test_absence_of_a_flight_is_recorded_once_across_two_runs_through_postgres(rolled_back_session):
    dsp_id = seeded_dsp_id(rolled_back_session)
    line = insert_campaign_line(rolled_back_session, "Absent flight", date(2026, 7, 1), date(2026, 8, 31))
    insert_mapping(rolled_back_session, line, dsp_id, validated_at=datetime(2026, 7, 20, 9, 0))
    july, august = replace_flights(rolled_back_session, line, [(date(2026, 7, 1), date(2026, 7, 31)),
                                                              (date(2026, 8, 1), date(2026, 8, 7))])
    batch_id = insert_ingestion_batch(rolled_back_session)
    service = DeliveryIngestionService(
        InMemoryDspDeliveryClient([]), lambda: SqlAlchemyUnitOfWork(lambda: rolled_back_session),
        lambda: datetime(2026, 8, 10, 2, 0))

    first = service.detect_missing_delivery(dsp_id, TODAY, batch_id)
    second = service.detect_missing_delivery(dsp_id, TODAY, batch_id)

    exception = rolled_back_session.scalars(select(IngestionExceptionRecord)).one()
    assert (first, second) == (1, 0)
    assert (exception.campaign_line_id, exception.campaign_period_id) == (line, august)
    assert july != august
