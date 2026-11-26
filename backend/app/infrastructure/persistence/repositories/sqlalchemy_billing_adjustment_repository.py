from datetime import datetime

from sqlalchemy import exists, select, text
from sqlalchemy.orm import Session

from app.domain.repositories.billing_adjustment_repository import AdjustableFlight, BillingAdjustmentTransaction
from app.domain.value_objects.billing import AdjustmentEntry, BillingAdjustment, BillingBasis
from app.domain.value_objects.flight import FlightWindow
from app.domain.value_objects.priced_flight import FlightFacts
from app.domain.value_objects.volume_commitment import VolumeCommitment
from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
)
from app.infrastructure.persistence.models.margin import AppliedRateRecord, FlightBillingAdjustmentRecord
from app.infrastructure.persistence.repositories.sqlalchemy_margin_repositories import (
    CLOSING_LOCK_NAMESPACE,
    _flight_facts,
    flight_facts_query,
)


def _entry(record: FlightBillingAdjustmentRecord) -> AdjustmentEntry:
    return AdjustmentEntry(
        entry_id=record.id, flight_id=record.campaign_line_period_id,
        adjustment=BillingAdjustment(BillingBasis(record.basis), record.amount), reason=record.reason,
        created_by=record.created_by, created_at=record.created_at,
    )


class SqlAlchemyBillingAdjustmentTransaction(BillingAdjustmentTransaction):
    """One database transaction on the caller's session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_flight(self, flight_id: int) -> AdjustableFlight | None:
        flight = CampaignLinePeriodRecord
        frozen = exists().where(AppliedRateRecord.campaign_line_period_id == flight.id)
        row = self._session.execute(
            select(
                flight.id, CampaignPeriodRecord.period_year, CampaignPeriodRecord.period_month, flight.flight_start,
                flight.flight_end, CampaignLineRecord.volume_commitment, frozen,
            )
            .select_from(flight)
            .join(CampaignLineRecord, CampaignLineRecord.id == flight.campaign_line_id)
            .join(CampaignPeriodRecord, CampaignPeriodRecord.id == flight.campaign_period_id)
            .where(flight.id == flight_id)
        ).one_or_none()
        if row is None:
            return None
        return AdjustableFlight(
            flight_id=row[0], window=FlightWindow(row[1], row[2], row[3], row[4]),
            volume_commitment=VolumeCommitment(row[5]), frozen=bool(row[6]),
        )

    def lock_month(self, year: int, month: int) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :key)"),
            {"namespace": CLOSING_LOCK_NAMESPACE, "key": year * 100 + month},
        )

    def flight_facts(self, flight_id: int) -> FlightFacts:
        row = self._session.execute(flight_facts_query().where(CampaignLinePeriodRecord.id == flight_id)).one()
        return _flight_facts(row)

    def add_adjustment(
        self, flight_id: int, adjustment: BillingAdjustment, reason: str, user_id: int, at: datetime
    ) -> AdjustmentEntry:
        record = FlightBillingAdjustmentRecord(
            campaign_line_period_id=flight_id, basis=adjustment.basis.value, amount=adjustment.amount, reason=reason,
            created_by=user_id, created_at=at,
        )
        self._session.add(record)
        self._session.flush()
        return _entry(record)

    def adjustments(self, flight_id: int) -> list[AdjustmentEntry]:
        records = self._session.scalars(
            select(FlightBillingAdjustmentRecord)
            .where(FlightBillingAdjustmentRecord.campaign_line_period_id == flight_id)
            .order_by(FlightBillingAdjustmentRecord.id.desc())
        )
        return [_entry(record) for record in records]

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
