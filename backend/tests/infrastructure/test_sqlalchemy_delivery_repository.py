"""The bulk write path: rows go to PostgreSQL in chunks, never as a list of entities."""

from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.domain.entities.ingestion_batch import BatchStatus, IngestionRoute
from app.domain.value_objects.delivery import DeliveryDateRange
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord, IngestionBatchRecord
from app.infrastructure.persistence.repositories.sqlalchemy_delivery_repository import (
    SqlAlchemyDeliveryRepository,
    SqlAlchemyIngestionBatchRepository,
)
from tests.fixtures.delivery_data import insert_campaign_line, insert_ingestion_batch
from tests.fixtures.delivery_rows import daily_delivery

WINDOW = DeliveryDateRange(date(2026, 8, 2), date(2026, 8, 4))


def _count(session) -> int:
    return session.scalar(select(func.count()).select_from(DailyDeliveryRecord))


def test_add_all_stores_every_row_with_its_exact_media_cost(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    batch_id = insert_ingestion_batch(rolled_back_session)
    repository = SqlAlchemyDeliveryRepository(rolled_back_session)

    repository.add_all([daily_delivery(line_id, date(2026, 8, 2), batch_id, media_cost=Decimal("1234.123457"))])

    assert rolled_back_session.scalars(select(DailyDeliveryRecord.media_cost)).one() == Decimal("1234.123457")


def test_add_all_writes_in_chunks_while_consuming_the_iterable_lazily(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    batch_id = insert_ingestion_batch(rolled_back_session)
    consumed_when_executing: list[int] = []
    consumed = 0

    def rows() -> Iterator:
        nonlocal consumed
        for day in range(1, 11):
            consumed += 1
            yield daily_delivery(line_id, date(2026, 9, day), batch_id)

    repository = SqlAlchemyDeliveryRepository(rolled_back_session, chunk_size=3)
    original_execute = rolled_back_session.execute

    def spying_execute(statement, params=None, *args, **kwargs):
        if isinstance(params, list):
            consumed_when_executing.append(consumed)
        return original_execute(statement, params, *args, **kwargs)

    rolled_back_session.execute = spying_execute
    repository.add_all(rows())

    assert consumed_when_executing == [3, 6, 9, 10]
    assert _count(rolled_back_session) == 10


def test_delete_range_removes_only_the_given_lines_inside_the_range(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    other_line_id = insert_campaign_line(rolled_back_session, campaign_name="Another delivery campaign")
    batch_id = insert_ingestion_batch(rolled_back_session)
    repository = SqlAlchemyDeliveryRepository(rolled_back_session)
    repository.add_all([
        daily_delivery(line_id, date(2026, 8, 1), batch_id),
        daily_delivery(line_id, date(2026, 8, 2), batch_id),
        daily_delivery(line_id, date(2026, 8, 4), batch_id),
        daily_delivery(line_id, date(2026, 8, 5), batch_id),
        daily_delivery(other_line_id, date(2026, 8, 3), batch_id),
    ])

    repository.delete_range([line_id], WINDOW)

    remaining = set(rolled_back_session.execute(
        select(DailyDeliveryRecord.campaign_line_id, DailyDeliveryRecord.delivery_date)).all())
    assert remaining == {(line_id, date(2026, 8, 1)), (line_id, date(2026, 8, 5)), (other_line_id, date(2026, 8, 3))}


def test_replacing_the_same_range_twice_leaves_one_row_per_line_and_day(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    batch_id = insert_ingestion_batch(rolled_back_session)
    repository = SqlAlchemyDeliveryRepository(rolled_back_session)

    for _ in range(2):
        repository.delete_range([line_id], WINDOW)
        repository.add_all([daily_delivery(line_id, date(2026, 8, 3), batch_id)])

    assert _count(rolled_back_session) == 1


def test_a_batch_is_started_running_and_finished_with_its_counts(rolled_back_session):
    dsp_batch_id = insert_ingestion_batch(rolled_back_session)
    dsp_id = rolled_back_session.get(IngestionBatchRecord, dsp_batch_id).dsp_id
    repository = SqlAlchemyIngestionBatchRepository(rolled_back_session)

    batch_id = repository.start(
        dsp_id, IngestionRoute.UPLOAD, "export.xlsx", datetime(2026, 8, 10, 2, 0),
        DeliveryDateRange(date(2026, 8, 3), date(2026, 8, 9)),
    )
    started = rolled_back_session.get(IngestionBatchRecord, batch_id)
    assert (started.status, started.route, started.source_file) == ("running", "upload", "export.xlsx")

    repository.finish(batch_id, BatchStatus.FAILED, datetime(2026, 8, 10, 2, 5), row_count=9, ignored_row_count=3,
                      zero_unmatched_row_count=4)
    rolled_back_session.expire_all()
    finished = rolled_back_session.get(IngestionBatchRecord, batch_id)
    assert (finished.status, finished.finished_at, finished.row_count, finished.ignored_row_count,
            finished.zero_unmatched_row_count) == ("failed", datetime(2026, 8, 10, 2, 5), 9, 3, 4)
