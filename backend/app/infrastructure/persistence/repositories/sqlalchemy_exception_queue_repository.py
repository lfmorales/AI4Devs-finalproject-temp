from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionSummary, ExceptionType
from app.domain.repositories.exception_queue_repository import ExceptionQueueRepository
from app.infrastructure.persistence.models.dsp_catalog import DspCatalogLineRecord
from app.infrastructure.persistence.models.delivery import (
    IngestionExceptionDeliveryRecord,
    IngestionExceptionRecord,
)


class SqlAlchemyExceptionQueueRepository(ExceptionQueueRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_summaries(self, status: ExceptionStatus | None) -> list[ExceptionSummary]:
        statement = self._summary_statement().order_by(
            IngestionExceptionRecord.last_date.desc().nulls_last(), IngestionExceptionRecord.id.desc()
        )
        if status is not None:
            statement = statement.where(IngestionExceptionRecord.status == status.value)
        return [_to_summary(row) for row in self._session.execute(statement)]

    def get_summary(self, exception_id: int) -> ExceptionSummary | None:
        row = self._session.execute(
            self._summary_statement().where(IngestionExceptionRecord.id == exception_id)
        ).one_or_none()
        return None if row is None else _to_summary(row)

    def mark_resolved(self, exception_id: int, resolved_at: datetime, resolved_by: int, note: str | None) -> bool:
        result = self._session.execute(
            update(IngestionExceptionRecord)
            .where(IngestionExceptionRecord.id == exception_id, IngestionExceptionRecord.status == "open")
            .values(status="resolved", resolved_at=resolved_at, resolved_by=resolved_by, note=note)
        )
        self._session.commit()
        return result.rowcount == 1

    @staticmethod
    def _summary_statement():
        retained = IngestionExceptionDeliveryRecord
        # Totals are summed in the database. Media cost is deliberately not selected.
        totals = (
            select(
                retained.exception_id.label("exception_id"),
                func.count().label("days"),
                func.sum(retained.impressions).label("impressions_total"),
                func.sum(retained.clicks).label("clicks_total"),
            )
            .group_by(retained.exception_id)
            .subquery()
        )
        exception = IngestionExceptionRecord
        return (
            select(
                exception,
                func.coalesce(totals.c.days, 0).label("days"),
                func.coalesce(totals.c.impressions_total, 0).label("impressions_total"),
                func.coalesce(totals.c.clicks_total, 0).label("clicks_total"),
                DspCatalogLineRecord.campaign_name.label("campaign_name"),
                DspCatalogLineRecord.line_item_name.label("line_item_name"),
            )
            .outerjoin(totals, totals.c.exception_id == exception.id)
            # At most one catalogue row per DSP and pair, so the join never repeats an exception.
            .outerjoin(
                DspCatalogLineRecord,
                (DspCatalogLineRecord.dsp_id == exception.dsp_id)
                & (DspCatalogLineRecord.external_campaign_id == exception.external_campaign_id)
                & (DspCatalogLineRecord.external_line_item_id == exception.external_line_item_id),
            )
        )


def _to_summary(row) -> ExceptionSummary:  # type: ignore[no-untyped-def]
    record: IngestionExceptionRecord = row[0]
    return ExceptionSummary(
        id=record.id,
        exception_type=ExceptionType(record.exception_type),
        status=ExceptionStatus(record.status),
        ingestion_batch_id=record.ingestion_batch_id,
        dsp_id=record.dsp_id,
        external_campaign_id=record.external_campaign_id,
        external_line_item_id=record.external_line_item_id,
        campaign_line_id=record.campaign_line_id,
        campaign_period_id=record.campaign_period_id,
        first_date=record.first_date,
        last_date=record.last_date,
        days=int(row.days),
        impressions_total=int(row.impressions_total),
        clicks_total=int(row.clicks_total),
        resolved_at=record.resolved_at,
        resolved_by=record.resolved_by,
        note=record.note,
        campaign_name=row.campaign_name,
        line_item_name=row.line_item_name,
    )
