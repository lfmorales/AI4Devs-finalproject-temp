from datetime import date

import pytest
from sqlalchemy import func, select

from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.fixtures.delivery_data import insert_campaign_line, insert_ingestion_batch
from tests.fixtures.delivery_rows import daily_delivery


def _count(session) -> int:
    return session.scalar(select(func.count()).select_from(DailyDeliveryRecord))


def test_leaving_the_block_commits(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    batch_id = insert_ingestion_batch(rolled_back_session)

    with SqlAlchemyUnitOfWork(lambda: rolled_back_session) as unit_of_work:
        unit_of_work.deliveries.add_all([daily_delivery(line_id, date(2026, 8, 5), batch_id)])

    assert _count(rolled_back_session) == 1


def test_an_error_inside_the_block_rolls_everything_back_and_propagates(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    batch_id = insert_ingestion_batch(rolled_back_session)
    rolled_back_session.commit()

    with pytest.raises(RuntimeError):
        with SqlAlchemyUnitOfWork(lambda: rolled_back_session) as unit_of_work:
            unit_of_work.deliveries.add_all([daily_delivery(line_id, date(2026, 8, 5), batch_id)])
            raise RuntimeError("fails after writing")

    assert _count(rolled_back_session) == 0


def test_it_exposes_every_repository_of_the_ingestion_run(rolled_back_session):
    with SqlAlchemyUnitOfWork(lambda: rolled_back_session) as unit_of_work:
        assert all(hasattr(unit_of_work, name) for name in ("deliveries", "batches", "targets", "exceptions"))
