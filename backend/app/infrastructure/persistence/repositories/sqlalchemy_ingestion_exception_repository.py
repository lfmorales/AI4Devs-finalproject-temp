from collections.abc import Iterable
from itertools import batched
from typing import Any

from sqlalchemy import delete, exists, func, insert, select, update
from sqlalchemy.orm import Session

from app.domain.entities.ingestion_exception import ExceptionType
from app.domain.repositories.ingestion_exception_repository import IngestionExceptionRepository
from app.domain.value_objects.delivery import DeliveryDateRange, ExternalLineKey, RetainedDelivery
from app.infrastructure.persistence.models.delivery import (
    IngestionExceptionDeliveryRecord,
    IngestionExceptionRecord,
)

_UNMATCHED = ExceptionType.UNMATCHED_DELIVERY.value
_MISSING = ExceptionType.MISSING_DELIVERY.value
_CHUNK_SIZE = 5000


class SqlAlchemyIngestionExceptionRepository(IngestionExceptionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def delete_retained_range(self, dsp_id: int, window: DeliveryDateRange) -> None:
        unmatched_of_dsp = select(IngestionExceptionRecord.id).where(
            IngestionExceptionRecord.exception_type == _UNMATCHED,
            IngestionExceptionRecord.dsp_id == dsp_id,
        )
        self._session.execute(
            delete(IngestionExceptionDeliveryRecord).where(
                IngestionExceptionDeliveryRecord.exception_id.in_(unmatched_of_dsp),
                IngestionExceptionDeliveryRecord.delivery_date.between(window.start, window.end),
            )
        )

    def get_or_create_unmatched(self, dsp_id: int, key: ExternalLineKey, batch_id: int) -> int:
        # No status in the filter: a resolved exception is found and left as it is, never reopened.
        existing = self._session.scalar(
            select(IngestionExceptionRecord.id).where(
                IngestionExceptionRecord.exception_type == _UNMATCHED,
                IngestionExceptionRecord.dsp_id == dsp_id,
                IngestionExceptionRecord.external_campaign_id == key.external_campaign_id,
                IngestionExceptionRecord.external_line_item_id == key.external_line_item_id,
            )
        )
        if existing is not None:
            return existing
        record = IngestionExceptionRecord(
            ingestion_batch_id=batch_id,
            exception_type=_UNMATCHED,
            status="open",
            dsp_id=dsp_id,
            external_campaign_id=key.external_campaign_id,
            external_line_item_id=key.external_line_item_id,
        )
        self._session.add(record)
        self._session.flush()
        return record.id

    def add_retained(self, exception_id: int, rows: Iterable[RetainedDelivery]) -> None:
        for chunk in batched(rows, _CHUNK_SIZE):
            self._session.execute(
                insert(IngestionExceptionDeliveryRecord), [_as_row(exception_id, row) for row in chunk]
            )

    def record_missing_delivery(self, campaign_line_id: int, campaign_period_id: int, batch_id: int) -> bool:
        already_recorded = self._session.scalar(
            select(exists().where(
                IngestionExceptionRecord.exception_type == _MISSING,
                IngestionExceptionRecord.campaign_line_id == campaign_line_id,
                IngestionExceptionRecord.campaign_period_id == campaign_period_id,
            ))
        )
        if already_recorded:
            return False
        self._session.add(IngestionExceptionRecord(
            ingestion_batch_id=batch_id,
            exception_type=_MISSING,
            status="open",
            campaign_line_id=campaign_line_id,
            campaign_period_id=campaign_period_id,
        ))
        self._session.flush()
        return True

    def refresh_unmatched_date_spans(self, dsp_id: int) -> None:
        retained = IngestionExceptionDeliveryRecord
        has_rows = exists().where(retained.exception_id == IngestionExceptionRecord.id)
        self._session.execute(
            update(IngestionExceptionRecord)
            .where(
                IngestionExceptionRecord.exception_type == _UNMATCHED,
                IngestionExceptionRecord.dsp_id == dsp_id,
                has_rows,
            )
            .values(
                first_date=select(func.min(retained.delivery_date))
                .where(retained.exception_id == IngestionExceptionRecord.id).scalar_subquery(),
                last_date=select(func.max(retained.delivery_date))
                .where(retained.exception_id == IngestionExceptionRecord.id).scalar_subquery(),
            )
        )


def _as_row(exception_id: int, row: RetainedDelivery) -> dict[str, Any]:
    return {
        "exception_id": exception_id,
        "delivery_date": row.delivery_date,
        "impressions": row.impressions,
        "clicks": row.clicks,
        "media_cost": row.media_cost,
        "measurable_impressions": row.measurable_impressions,
        "viewable_impressions": row.viewable_impressions,
    }
