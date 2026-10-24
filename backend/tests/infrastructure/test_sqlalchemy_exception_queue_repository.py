"""The exception queue against PostgreSQL: totals aggregated in the database, no cost, resolution only marks."""

from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionSummary
from app.domain.value_objects.delivery import ExternalLineKey, RetainedDelivery
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord, IngestionExceptionDeliveryRecord
from app.infrastructure.persistence.repositories.sqlalchemy_exception_queue_repository import (
    SqlAlchemyExceptionQueueRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_ingestion_exception_repository import (
    SqlAlchemyIngestionExceptionRepository,
)
from tests.fixtures.delivery_data import (
    insert_campaign_line,
    insert_ingestion_batch,
    insert_user,
    seeded_dsp_id,
)

NOW = datetime(2026, 8, 10, 9, 0)


def _retained(day: int, key: ExternalLineKey, impressions: int, clicks: int, cost: str) -> RetainedDelivery:
    return RetainedDelivery(key, date(2026, 8, day), impressions, clicks, Decimal(cost), 1, 1)


def _seed_unmatched(session, key: ExternalLineKey = ExternalLineKey("9", "9")) -> int:
    repository = SqlAlchemyIngestionExceptionRepository(session)
    batch_id = insert_ingestion_batch(session)
    exception_id = repository.get_or_create_unmatched(seeded_dsp_id(session), key, batch_id)
    repository.add_retained(exception_id, [
        _retained(3, key, 100, 4, "1.500000"), _retained(5, key, 250, 6, "2.250000"), _retained(8, key, 50, 1, "0.1"),
    ])
    repository.refresh_unmatched_date_spans(seeded_dsp_id(session))
    return exception_id


def test_an_unmatched_exception_shows_dates_days_and_totals(rolled_back_session):
    exception_id = _seed_unmatched(rolled_back_session)

    summary = SqlAlchemyExceptionQueueRepository(rolled_back_session).get_summary(exception_id)

    assert (summary.first_date, summary.last_date, summary.days) == (date(2026, 8, 3), date(2026, 8, 8), 3)
    assert (summary.impressions_total, summary.clicks_total) == (400, 11)
    assert (summary.external_campaign_id, summary.external_line_item_id) == ("9", "9")


def test_the_summary_carries_no_cost_field(rolled_back_session):
    names = {field.name for field in fields(ExceptionSummary)}

    assert not any("cost" in name for name in names)


def test_a_missing_delivery_exception_has_no_retained_days(rolled_back_session):
    line = insert_campaign_line(rolled_back_session)
    from app.infrastructure.persistence.models.campaign import CampaignLineRecord

    period = rolled_back_session.get(CampaignLineRecord, line).campaign_period_id
    SqlAlchemyIngestionExceptionRepository(rolled_back_session).record_missing_delivery(
        line, period, insert_ingestion_batch(rolled_back_session))

    summary = SqlAlchemyExceptionQueueRepository(rolled_back_session).list_summaries(None)[0]

    assert (summary.days, summary.impressions_total, summary.clicks_total) == (0, 0, 0)
    assert (summary.campaign_line_id, summary.campaign_period_id) == (line, period)


def test_listing_filters_by_status_and_orders_by_id(rolled_back_session):
    first = _seed_unmatched(rolled_back_session, ExternalLineKey("1", "1"))
    second = _seed_unmatched(rolled_back_session, ExternalLineKey("2", "2"))
    queue = SqlAlchemyExceptionQueueRepository(rolled_back_session)
    queue.mark_resolved(first, NOW, insert_user(rolled_back_session), None)

    assert [s.id for s in queue.list_summaries(None)] == [first, second]
    assert [s.id for s in queue.list_summaries(ExceptionStatus.OPEN)] == [second]
    assert [s.id for s in queue.list_summaries(ExceptionStatus.RESOLVED)] == [first]


def test_a_missing_exception_has_no_summary(rolled_back_session):
    assert SqlAlchemyExceptionQueueRepository(rolled_back_session).get_summary(0) is None


def test_resolving_records_the_time_the_user_and_the_note(rolled_back_session):
    exception_id = _seed_unmatched(rolled_back_session)
    user_id = insert_user(rolled_back_session)
    queue = SqlAlchemyExceptionQueueRepository(rolled_back_session)

    marked = queue.mark_resolved(exception_id, NOW, user_id, "Typo")

    summary = queue.get_summary(exception_id)
    assert marked is True
    assert (summary.status, summary.resolved_at, summary.resolved_by, summary.note) == (
        ExceptionStatus.RESOLVED, NOW, user_id, "Typo")


def test_resolving_twice_marks_nothing_the_second_time_and_keeps_the_first_resolution(rolled_back_session):
    exception_id = _seed_unmatched(rolled_back_session)
    first_user, second_user = insert_user(rolled_back_session), insert_user(rolled_back_session, "second@example.com")
    queue = SqlAlchemyExceptionQueueRepository(rolled_back_session)
    queue.mark_resolved(exception_id, NOW, first_user, "first")

    marked = queue.mark_resolved(exception_id, NOW, second_user, "second")

    assert marked is False
    assert queue.get_summary(exception_id).resolved_by == first_user


def test_resolving_does_not_reprocess_or_move_the_retained_delivery(rolled_back_session):
    exception_id = _seed_unmatched(rolled_back_session)
    queue = SqlAlchemyExceptionQueueRepository(rolled_back_session)

    queue.mark_resolved(exception_id, NOW, insert_user(rolled_back_session), None)

    retained = rolled_back_session.scalar(select(func.count()).select_from(IngestionExceptionDeliveryRecord))
    daily = rolled_back_session.scalar(select(func.count()).select_from(DailyDeliveryRecord))
    assert (retained, daily) == (3, 0)
    assert queue.get_summary(exception_id).impressions_total == 400
