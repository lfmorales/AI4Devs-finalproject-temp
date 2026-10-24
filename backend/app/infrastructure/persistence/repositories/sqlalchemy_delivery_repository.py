from collections.abc import Collection, Iterable
from datetime import datetime
from itertools import batched
from typing import Any

from sqlalchemy import delete, insert, update
from sqlalchemy.orm import Session

from app.domain.entities.ingestion_batch import BatchStatus, IngestionRoute
from app.domain.repositories.delivery_repository import DeliveryRepository
from app.domain.repositories.ingestion_batch_repository import IngestionBatchRepository
from app.domain.value_objects.delivery import DailyDelivery, DeliveryDateRange
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord, IngestionBatchRecord

DEFAULT_CHUNK_SIZE = 5000


class SqlAlchemyDeliveryRepository(DeliveryRepository):
    """Writes deliveries with set-based statements; no ORM entity is ever built for a delivery row."""

    def __init__(self, session: Session, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self._session = session
        self._chunk_size = chunk_size

    def delete_range(self, campaign_line_ids: Collection[int], date_range: DeliveryDateRange) -> None:
        self._session.execute(
            delete(DailyDeliveryRecord).where(
                DailyDeliveryRecord.campaign_line_id.in_(campaign_line_ids),
                DailyDeliveryRecord.delivery_date.between(date_range.start, date_range.end),
            )
        )

    def add_all(self, deliveries: Iterable[DailyDelivery]) -> None:
        # batched() pulls one chunk at a time from the iterable, so memory follows the chunk, not the run.
        for chunk in batched(deliveries, self._chunk_size):
            self._session.execute(insert(DailyDeliveryRecord), [_as_row(delivery) for delivery in chunk])


def _as_row(delivery: DailyDelivery) -> dict[str, Any]:
    return {
        "campaign_line_id": delivery.campaign_line_id,
        "ingestion_batch_id": delivery.ingestion_batch_id,
        "delivery_date": delivery.delivery_date,
        "impressions": delivery.impressions,
        "clicks": delivery.clicks,
        "media_cost": delivery.media_cost,
        "measurable_impressions": delivery.measurable_impressions,
        "viewable_impressions": delivery.viewable_impressions,
        "banner_size": delivery.banner_size,
        "screen": delivery.screen,
        "line_format": delivery.line_format,
    }


class SqlAlchemyIngestionBatchRepository(IngestionBatchRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def start(self, dsp_id: int, route: IngestionRoute, source_file: str | None, started_at: datetime) -> int:
        record = IngestionBatchRecord(
            dsp_id=dsp_id,
            route=route.value,
            source_file=source_file,
            started_at=started_at,
            status=BatchStatus.RUNNING.value,
            row_count=0,
            ignored_row_count=0,
        )
        self._session.add(record)
        self._session.flush()
        return record.id

    def finish(
        self, batch_id: int, status: BatchStatus, finished_at: datetime, row_count: int, ignored_row_count: int
    ) -> None:
        self._session.execute(
            update(IngestionBatchRecord)
            .where(IngestionBatchRecord.id == batch_id)
            .values(status=status.value, finished_at=finished_at, row_count=row_count,
                    ignored_row_count=ignored_row_count)
        )
