"""The ingestion service through PostgreSQL: the same window twice, and a resolved pair that delivers again."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.services.delivery_ingestion_service import DeliveryIngestionService
from app.domain.entities.ingestion_batch import IngestionRoute
from app.domain.value_objects.delivery import ExternalLineKey
from app.infrastructure.dsp.adform_delivery_client import AdformDeliveryClient
from app.infrastructure.dsp.equativ_delivery_client import EquativDeliveryClient
from app.infrastructure.persistence.models.delivery import (
    DailyDeliveryRecord,
    IngestionBatchRecord,
    IngestionExceptionDeliveryRecord,
    IngestionExceptionRecord,
)
from app.infrastructure.persistence.models.dsp_catalog import DspCatalogLineRecord
from app.infrastructure.persistence.models.masters import DSPRecord
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
from tests.fixtures.fake_adform import FakeAdform, report_row
from tests.fixtures.fake_equativ import FakeEquativ, package_row
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


def test_delivery_outside_every_flight_of_its_line_is_stored_all_the_same(rolled_back_session):
    setup = _Setup(rolled_back_session, [dsp_row(D5, MAPPED, impressions=700)])
    replace_flights(rolled_back_session, setup.line_id, [(date(2026, 8, 1), date(2026, 8, 2))])  # the 5th is outside

    setup.run()

    stored = rolled_back_session.scalars(select(DailyDeliveryRecord)).one()
    assert (stored.campaign_line_id, stored.delivery_date, stored.impressions) == (setup.line_id, D5, 700)


def test_a_dooh_line_and_a_ctv_line_of_an_adform_report_are_stored_with_their_ots_and_completions(
    rolled_back_session: Session,
) -> None:
    dsp_id = seeded_dsp_id(rolled_back_session)
    dooh_line = insert_campaign_line(rolled_back_session, "DOOH campaign")
    ctv_line = insert_campaign_line(rolled_back_session, "CTV campaign")
    insert_mapping(rolled_back_session, dooh_line, dsp_id, "1001", "2001")
    insert_mapping(rolled_back_session, ctv_line, dsp_id, "1001", "2002")
    fake = FakeAdform(rows=[
        report_row(line_item_id=2001, impressions=500, ots="8999.75"),
        report_row(line_item_id=2002, impressions=50000, completion_rate="0.8123"),
    ])
    client = AdformDeliveryClient(
        client_id="synthetic-client-id", client_secret="synthetic-client-secret", http_client=fake.client(),
        sleep=lambda _seconds: None, today=lambda: TODAY)
    service = DeliveryIngestionService(
        client, lambda: SqlAlchemyUnitOfWork(lambda: rolled_back_session), lambda: datetime(2026, 8, 10, 2, 0))

    service.run(dsp_id, TODAY, route=IngestionRoute.API)

    stored = {row.campaign_line_id: row for row in rolled_back_session.scalars(select(DailyDeliveryRecord))}
    assert (stored[dooh_line].impressions, stored[dooh_line].ots, stored[dooh_line].video_completions) == (
        500, Decimal("8999.7500"), 0)
    assert (stored[ctv_line].impressions, stored[ctv_line].ots, stored[ctv_line].video_completions) == (
        50000, Decimal("0.0000"), 40615)


def test_an_equativ_run_fills_one_catalogue_row_per_package_with_no_mapping_at_all(rolled_back_session: Session) -> None:
    equativ = DSPRecord(name="Equativ", is_active=True)
    rolled_back_session.add(equativ)
    rolled_back_session.flush()
    zero_width_name = "Synthetic​ Package Two"
    fake = FakeEquativ(rows=[
        package_row(day="2026-11-19T00:00:00", package_id="900000001", name="Synthetic Package One", impressions="500"),
        package_row(day="2026-11-21T00:00:00", package_id="900000001", name="Synthetic Package One", impressions="0"),
        package_row(day="2026-11-20T00:00:00", package_id="900000002", name=zero_width_name, impressions="70"),
    ])
    client = EquativDeliveryClient("synthetic-id", "synthetic-secret", fake.client(), sleep=lambda _: None,
                                   monotonic=lambda: 0.0)
    service = DeliveryIngestionService(
        client, lambda: SqlAlchemyUnitOfWork(lambda: rolled_back_session), lambda: datetime(2026, 11, 24, 6, 15))

    service.run(equativ.id, date(2026, 11, 24))

    rows = rolled_back_session.scalars(
        select(DspCatalogLineRecord).where(DspCatalogLineRecord.dsp_id == equativ.id)
        .order_by(DspCatalogLineRecord.external_campaign_id)
    ).all()
    assert [
        (r.external_campaign_id, r.external_line_item_id, r.campaign_name, r.line_item_name, r.line_start_date,
         r.line_end_date, r.first_seen_date, r.last_seen_date, r.last_impressions_date)
        for r in rows
    ] == [
        ("900000001", "900000001", "Synthetic Package One", "Synthetic Package One", None, None,
         date(2026, 11, 19), date(2026, 11, 21), date(2026, 11, 19)),
        ("900000002", "900000002", zero_width_name, zero_width_name, None, None,
         date(2026, 11, 20), date(2026, 11, 20), date(2026, 11, 20)),
    ]
    assert "​" in rows[1].campaign_name
    assert rolled_back_session.scalar(select(func.count()).select_from(DailyDeliveryRecord)) == 0
