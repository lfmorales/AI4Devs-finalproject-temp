from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric, cast, exists, func, select, text, update
from sqlalchemy.orm import Session

from app.domain.repositories.carryover_repository import CarryoverFlight, CarryoverTransaction, LineFlight
from app.domain.services.carryover import PreviousFlight
from app.domain.value_objects.flight import FlightWindow
from app.domain.value_objects.review import ReviewCause
from app.domain.value_objects.volume_commitment import VolumeCommitment
from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
)
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord
from app.infrastructure.persistence.models.margin import MonthClosingRecord
from app.infrastructure.persistence.models.masters import ChannelRecord
from app.infrastructure.persistence.repositories import sqlalchemy_review_repository as reviews
from app.infrastructure.persistence.repositories.delivered_volume import delivered_in_channel_metric
from app.infrastructure.persistence.repositories.sqlalchemy_margin_repositories import CLOSING_LOCK_NAMESPACE


class SqlAlchemyCarryoverTransaction(CarryoverTransaction):
    """One database transaction on the caller's session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_flight(self, flight_id: int) -> CarryoverFlight | None:
        flight = CampaignLinePeriodRecord
        # The month is closed when it holds a closing header (finance/rebate-accrual), whichever flights it froze.
        month_closed = exists().where(
            MonthClosingRecord.period_year == CampaignPeriodRecord.period_year,
            MonthClosingRecord.period_month == CampaignPeriodRecord.period_month,
        )
        row = self._session.execute(
            select(
                flight.id, flight.campaign_line_id, CampaignPeriodRecord.period_year, CampaignPeriodRecord.period_month,
                flight.flight_start, flight.flight_end, flight.contracted_impressions, flight.carryover,
                flight.carryover_billable, ChannelRecord.delivery_metric, CampaignLineRecord.volume_commitment,
                month_closed,
            )
            .select_from(flight)
            .join(CampaignLineRecord, CampaignLineRecord.id == flight.campaign_line_id)
            .join(ChannelRecord, ChannelRecord.id == CampaignLineRecord.channel_id)
            .join(CampaignPeriodRecord, CampaignPeriodRecord.id == flight.campaign_period_id)
            .where(flight.id == flight_id)
        ).one_or_none()
        if row is None:
            return None
        return CarryoverFlight(
            flight_id=row[0], line_id=row[1], window=FlightWindow(row[2], row[3], row[4], row[5]),
            contracted=int(row[6]), carryover=int(row[7]), carryover_billable=bool(row[8]), delivery_metric=row[9],
            volume_commitment=VolumeCommitment(row[10]), month_closed=bool(row[11]),
        )

    def lock_month(self, year: int, month: int) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :key)"),
            {"namespace": CLOSING_LOCK_NAMESPACE, "key": year * 100 + month},
        )

    def line_flights(self, line_id: int) -> list[LineFlight]:
        rows = self._session.execute(
            select(
                CampaignLinePeriodRecord.id, CampaignPeriodRecord.period_year, CampaignPeriodRecord.period_month,
                CampaignLinePeriodRecord.flight_start, CampaignLinePeriodRecord.flight_end,
            )
            .join(CampaignPeriodRecord, CampaignPeriodRecord.id == CampaignLinePeriodRecord.campaign_period_id)
            .where(CampaignLinePeriodRecord.campaign_line_id == line_id)
            .order_by(CampaignLinePeriodRecord.flight_start)
        ).all()
        return [LineFlight(row[0], FlightWindow(row[1], row[2], row[3], row[4])) for row in rows]

    def previous_flight_figures(self, flight_id: int) -> PreviousFlight:
        flight = CampaignLinePeriodRecord
        # Summed in the database in the unit the line's channel counts in, as a four-decimal number.
        delivered = (
            select(cast(func.coalesce(func.sum(delivered_in_channel_metric()), 0), Numeric(18, 4)))
            .where(
                DailyDeliveryRecord.campaign_line_id == flight.campaign_line_id,
                DailyDeliveryRecord.delivery_date.between(flight.flight_start, flight.flight_end),
            )
            .scalar_subquery()
        )
        row = self._session.execute(
            select(flight.flight_end, flight.contracted_impressions + flight.carryover, delivered)
            .select_from(flight)
            .join(CampaignLineRecord, CampaignLineRecord.id == flight.campaign_line_id)
            .join(ChannelRecord, ChannelRecord.id == CampaignLineRecord.channel_id)
            .where(flight.id == flight_id)
        ).one()
        return PreviousFlight(flight_end=row[0], delivery_target=int(row[1]), delivered=Decimal(row[2]))

    def write_carryover(self, flight_id: int, volume: int, reason: str, user_id: int, at: datetime) -> None:
        self._session.execute(
            update(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.id == flight_id).values(
                carryover=volume, carryover_reason=reason, carryover_set_by=user_id, carryover_set_at=at,
            )
        )
        self._session.flush()

    def write_billable(self, flight_id: int, billable: bool, user_id: int, at: datetime) -> None:
        self._session.execute(
            update(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.id == flight_id).values(
                carryover_billable=billable, carryover_billable_set_by=user_id, carryover_billable_set_at=at,
            )
        )
        self._session.flush()

    def reopen_review_if_reviewed(self, flight_id: int, cause: ReviewCause, user_id: int, at: datetime) -> None:
        reviews.reopen_review_if_reviewed(self._session, flight_id, cause, user_id, at)

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
