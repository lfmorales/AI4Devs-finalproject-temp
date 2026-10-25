"""The exception repository against PostgreSQL: one exception per DSP and pair, retained delivery replaced by date."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from app.domain.value_objects.delivery import DeliveryDateRange, ExternalLineKey, RetainedDelivery
from app.infrastructure.persistence.models.delivery import (
    IngestionExceptionDeliveryRecord,
    IngestionExceptionRecord,
)
from app.infrastructure.persistence.repositories.sqlalchemy_ingestion_exception_repository import (
    SqlAlchemyIngestionExceptionRepository,
)
from tests.fixtures.delivery_data import insert_ingestion_batch, insert_other_dsp, insert_user, seeded_dsp_id

KEY = ExternalLineKey("9", "9")
WINDOW = DeliveryDateRange(date(2026, 8, 3), date(2026, 8, 9))


def _row(day: date, key: ExternalLineKey = KEY, impressions: int = 40, cost: str = "1.234567") -> RetainedDelivery:
    return RetainedDelivery(key, day, impressions, 2, Decimal(cost), 30, 20)


def _retained_dates(session, exception_id: int) -> list[date]:
    return sorted(session.scalars(select(IngestionExceptionDeliveryRecord.delivery_date).where(
        IngestionExceptionDeliveryRecord.exception_id == exception_id)))


def test_an_exception_is_created_open_with_its_dsp_pair_and_batch(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    dsp_id = seeded_dsp_id(rolled_back_session)

    exception_id = SqlAlchemyIngestionExceptionRepository(rolled_back_session).get_or_create_unmatched(
        dsp_id, KEY, batch_id)

    record = rolled_back_session.get(IngestionExceptionRecord, exception_id)
    assert (record.exception_type, record.status, record.dsp_id, record.ingestion_batch_id) == (
        "unmatched_delivery", "open", dsp_id, batch_id)
    assert (record.external_campaign_id, record.external_line_item_id) == ("9", "9")


def test_asking_again_returns_the_same_exception(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    dsp_id = seeded_dsp_id(rolled_back_session)
    repository = SqlAlchemyIngestionExceptionRepository(rolled_back_session)

    first = repository.get_or_create_unmatched(dsp_id, KEY, batch_id)
    second = repository.get_or_create_unmatched(dsp_id, KEY, insert_ingestion_batch(rolled_back_session))

    assert first == second


def test_a_resolved_exception_is_returned_untouched_not_reopened(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    dsp_id = seeded_dsp_id(rolled_back_session)
    user_id = insert_user(rolled_back_session)
    repository = SqlAlchemyIngestionExceptionRepository(rolled_back_session)
    exception_id = repository.get_or_create_unmatched(dsp_id, KEY, batch_id)
    record = rolled_back_session.get(IngestionExceptionRecord, exception_id)
    record.status, record.resolved_at, record.resolved_by, record.note = (
        "resolved", datetime(2026, 8, 8, 9, 0), user_id, "typo")
    rolled_back_session.flush()

    again = repository.get_or_create_unmatched(dsp_id, KEY, batch_id)

    rolled_back_session.expire_all()
    stored = rolled_back_session.get(IngestionExceptionRecord, again)
    assert (again, stored.status, stored.note) == (exception_id, "resolved", "typo")


def test_the_same_pair_for_another_dsp_is_another_exception(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    repository = SqlAlchemyIngestionExceptionRepository(rolled_back_session)

    one = repository.get_or_create_unmatched(seeded_dsp_id(rolled_back_session), KEY, batch_id)
    other = repository.get_or_create_unmatched(insert_other_dsp(rolled_back_session), KEY, batch_id)

    assert one != other


def test_retained_delivery_keeps_six_decimals(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    repository = SqlAlchemyIngestionExceptionRepository(rolled_back_session)
    exception_id = repository.get_or_create_unmatched(seeded_dsp_id(rolled_back_session), KEY, batch_id)

    repository.add_retained(exception_id, [_row(date(2026, 8, 5), cost="12.345678")])

    assert rolled_back_session.scalars(select(IngestionExceptionDeliveryRecord.media_cost)).one() == Decimal("12.345678")


def test_deleting_a_range_removes_only_that_dsps_retained_dates_inside_it(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    dsp_id = seeded_dsp_id(rolled_back_session)
    other_dsp = insert_other_dsp(rolled_back_session)
    repository = SqlAlchemyIngestionExceptionRepository(rolled_back_session)
    mine = repository.get_or_create_unmatched(dsp_id, KEY, batch_id)
    theirs = repository.get_or_create_unmatched(other_dsp, KEY, batch_id)
    for exception_id in (mine, theirs):
        repository.add_retained(exception_id, [_row(date(2026, 8, day)) for day in (1, 3, 9, 12)])

    repository.delete_retained_range(dsp_id, WINDOW)

    assert _retained_dates(rolled_back_session, mine) == [date(2026, 8, 1), date(2026, 8, 12)]
    assert len(_retained_dates(rolled_back_session, theirs)) == 4


def test_date_spans_are_set_from_the_retained_delivery(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    dsp_id = seeded_dsp_id(rolled_back_session)
    repository = SqlAlchemyIngestionExceptionRepository(rolled_back_session)
    exception_id = repository.get_or_create_unmatched(dsp_id, KEY, batch_id)
    repository.add_retained(exception_id, [_row(date(2026, 8, 7)), _row(date(2026, 8, 4)), _row(date(2026, 8, 6))])

    repository.refresh_unmatched_date_spans(dsp_id)

    rolled_back_session.expire_all()
    record = rolled_back_session.get(IngestionExceptionRecord, exception_id)
    assert (record.first_date, record.last_date) == (date(2026, 8, 4), date(2026, 8, 7))


def test_an_exception_with_no_retained_delivery_keeps_its_dates(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    dsp_id = seeded_dsp_id(rolled_back_session)
    repository = SqlAlchemyIngestionExceptionRepository(rolled_back_session)
    exception_id = repository.get_or_create_unmatched(dsp_id, KEY, batch_id)
    record = rolled_back_session.get(IngestionExceptionRecord, exception_id)
    record.first_date, record.last_date = date(2026, 8, 1), date(2026, 8, 2)
    rolled_back_session.flush()

    repository.refresh_unmatched_date_spans(dsp_id)

    rolled_back_session.expire_all()
    record = rolled_back_session.get(IngestionExceptionRecord, exception_id)
    assert (record.first_date, record.last_date) == (date(2026, 8, 1), date(2026, 8, 2))
