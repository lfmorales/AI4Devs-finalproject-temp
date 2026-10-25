"""A batch records the window it replaced: both ends or neither, the start not after the end."""

from datetime import date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.entities.ingestion_batch import IngestionRoute
from app.domain.value_objects.delivery import DeliveryDateRange
from app.infrastructure.persistence.models.delivery import IngestionBatchRecord
from app.infrastructure.persistence.repositories.sqlalchemy_delivery_repository import (
    SqlAlchemyIngestionBatchRepository,
)
from tests.fixtures.delivery_data import seeded_dsp_id


def _record(session, start: date | None, end: date | None) -> IngestionBatchRecord:
    return IngestionBatchRecord(
        dsp_id=seeded_dsp_id(session), route="api", started_at=datetime(2026, 8, 10, 2, 0), status="running",
        row_count=0, window_start=start, window_end=end,
    )


@pytest.mark.parametrize("start,end", [(None, None), (date(2026, 8, 3), date(2026, 8, 9)), (date(2026, 8, 3), date(2026, 8, 3))])
def test_both_ends_or_neither_are_accepted(rolled_back_session, start, end):
    rolled_back_session.add(_record(rolled_back_session, start, end))

    rolled_back_session.flush()


@pytest.mark.parametrize("start,end", [
    (date(2026, 8, 3), None), (None, date(2026, 8, 9)), (date(2026, 8, 9), date(2026, 8, 3)),
])
def test_one_end_alone_or_a_start_after_the_end_is_refused(rolled_back_session, start, end):
    rolled_back_session.add(_record(rolled_back_session, start, end))

    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_a_started_batch_stores_its_window(rolled_back_session):
    repository = SqlAlchemyIngestionBatchRepository(rolled_back_session)

    batch_id = repository.start(
        seeded_dsp_id(rolled_back_session), IngestionRoute.API, None, datetime(2026, 8, 10, 2, 0),
        DeliveryDateRange(date(2026, 8, 3), date(2026, 8, 9)),
    )

    stored = rolled_back_session.get(IngestionBatchRecord, batch_id)
    assert (stored.window_start, stored.window_end) == (date(2026, 8, 3), date(2026, 8, 9))
