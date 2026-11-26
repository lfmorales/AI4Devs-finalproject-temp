from calendar import monthrange
from datetime import date, datetime

from sqlalchemy import exists, func, select, text
from sqlalchemy.orm import Session

from app.domain.repositories.monthly_review_repository import MonthlyReviewTransaction, ReviewEvent
from app.domain.services.monthly_review import FlightCounts
from app.domain.value_objects.review import ReviewCause, ReviewKind
from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
)
from app.infrastructure.persistence.models.delivery import IngestionBatchRecord
from app.infrastructure.persistence.models.margin import AppliedRateRecord, CampaignPeriodReviewRecord
from app.infrastructure.persistence.models.masters import DSPRecord
from app.infrastructure.persistence.repositories.sqlalchemy_margin_repositories import CLOSING_LOCK_NAMESPACE


def _event(record: CampaignPeriodReviewRecord) -> ReviewEvent:
    return ReviewEvent(
        kind=ReviewKind(record.kind), cause=None if record.cause is None else ReviewCause(record.cause),
        created_by=record.created_by, created_at=record.created_at,
    )


def _latest_event(session: Session, period_id: int) -> CampaignPeriodReviewRecord | None:
    return session.scalars(
        select(CampaignPeriodReviewRecord).where(CampaignPeriodReviewRecord.campaign_period_id == period_id)
        .order_by(CampaignPeriodReviewRecord.id.desc()).limit(1)
    ).first()


def reopen_review_if_reviewed(
    session: Session, flight_id: int, cause: ReviewCause, user_id: int, at: datetime
) -> bool:
    """Record a reopening of the flight's campaign in the flight's month when its latest event there is a review.

    It runs on the session of the edit that calls it, so the reopening and the edit are written, or lost, together. A
    campaign that is not reviewed gets nothing: an edit of one pending review changes no state. True when it wrote.
    """
    period_id = session.scalar(
        select(CampaignLinePeriodRecord.campaign_period_id).where(CampaignLinePeriodRecord.id == flight_id)
    )
    if period_id is None:
        return False
    latest = _latest_event(session, period_id)
    if latest is None or latest.kind != ReviewKind.REVIEWED.value:
        return False
    session.add(CampaignPeriodReviewRecord(
        campaign_period_id=period_id, kind=ReviewKind.REOPENED.value, cause=cause.value,
        campaign_line_period_id=flight_id, created_by=user_id, created_at=at,
    ))
    session.flush()
    return True


class SqlAlchemyMonthlyReviewTransaction(MonthlyReviewTransaction):
    """One database transaction on the caller's session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def campaign_exists(self, campaign_id: int) -> bool:
        return bool(self._session.scalar(select(exists().where(CampaignRecord.id == campaign_id))))

    def period_of(self, campaign_id: int, year: int, month: int) -> int | None:
        return self._session.scalar(
            select(CampaignPeriodRecord.id).where(
                CampaignPeriodRecord.campaign_id == campaign_id, CampaignPeriodRecord.period_year == year,
                CampaignPeriodRecord.period_month == month,
            )
        )

    def lock_month(self, year: int, month: int) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :key)"),
            {"namespace": CLOSING_LOCK_NAMESPACE, "key": year * 100 + month},
        )

    def flight_counts(self, period_id: int, as_of: date) -> FlightCounts:
        flight = CampaignLinePeriodRecord
        frozen = exists().where(AppliedRateRecord.campaign_line_period_id == flight.id)
        total, ended, frozen_count = self._session.execute(
            select(
                func.count(),
                func.count().filter(flight.flight_end <= as_of),
                func.count().filter(frozen),
            ).where(flight.campaign_period_id == period_id)
        ).one()
        return FlightCounts(total=int(total), ended=int(ended), frozen=int(frozen_count))

    def dsps_without_the_months_last_day(self, period_id: int, year: int, month: int) -> list[str]:
        last_day = date(year, month, monthrange(year, month)[1])
        loaded = exists().where(
            IngestionBatchRecord.dsp_id == CampaignLineRecord.dsp_id,
            IngestionBatchRecord.status == "succeeded",
            IngestionBatchRecord.window_start <= last_day,
            IngestionBatchRecord.window_end >= last_day,
        )
        return list(self._session.scalars(
            select(DSPRecord.name)
            .select_from(CampaignLinePeriodRecord)
            .join(CampaignLineRecord, CampaignLineRecord.id == CampaignLinePeriodRecord.campaign_line_id)
            .join(DSPRecord, DSPRecord.id == CampaignLineRecord.dsp_id)
            .where(CampaignLinePeriodRecord.campaign_period_id == period_id, ~loaded)
            .distinct()
            .order_by(DSPRecord.name)
        ))

    def latest_event(self, period_id: int) -> ReviewEvent | None:
        record = _latest_event(self._session, period_id)
        return None if record is None else _event(record)

    def add_event(
        self, period_id: int, kind: ReviewKind, cause: ReviewCause | None, flight_id: int | None, user_id: int,
        at: datetime,
    ) -> ReviewEvent:
        record = CampaignPeriodReviewRecord(
            campaign_period_id=period_id, kind=kind.value, cause=None if cause is None else cause.value,
            campaign_line_period_id=flight_id, created_by=user_id, created_at=at,
        )
        self._session.add(record)
        self._session.flush()
        return _event(record)

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
