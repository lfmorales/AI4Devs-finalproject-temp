from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.domain.entities.campaign_status import FlightDeliveryFigures
from app.domain.repositories.campaign_status_repository import CampaignStatusRepository
from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
)
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord
from app.infrastructure.persistence.models.masters import AgencyRecord


class SqlAlchemyCampaignStatusRepository(CampaignStatusRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_running_flights(self, as_of: date) -> list[FlightDeliveryFigures]:
        flight = CampaignLinePeriodRecord
        # Both aggregates run in the database over the indexed (line, date) pair: no delivery row is fetched.
        delivered = (
            select(func.coalesce(func.sum(DailyDeliveryRecord.impressions), 0))
            .where(
                DailyDeliveryRecord.campaign_line_id == flight.campaign_line_id,
                DailyDeliveryRecord.delivery_date.between(flight.flight_start, as_of),
            )
            .scalar_subquery()
        )
        sibling_line = aliased(CampaignLineRecord)
        latest_of_campaign = (
            select(func.max(DailyDeliveryRecord.delivery_date))
            .join(sibling_line, sibling_line.id == DailyDeliveryRecord.campaign_line_id)
            .where(sibling_line.campaign_id == CampaignRecord.id)
            .scalar_subquery()
        )
        rows = self._session.execute(
            select(
                CampaignRecord.id, CampaignRecord.name, AgencyRecord.id, AgencyRecord.name,
                CampaignLineRecord.line_number, flight.campaign_period_id,
                CampaignPeriodRecord.period_year, CampaignPeriodRecord.period_month,
                flight.flight_start, flight.flight_end, flight.contracted_impressions,
                delivered, latest_of_campaign,
            )
            .select_from(flight)
            .join(CampaignLineRecord, CampaignLineRecord.id == flight.campaign_line_id)
            .join(CampaignRecord, CampaignRecord.id == CampaignLineRecord.campaign_id)
            .join(AgencyRecord, AgencyRecord.id == CampaignRecord.agency_id)
            .join(CampaignPeriodRecord, CampaignPeriodRecord.id == flight.campaign_period_id)
            .where(
                CampaignRecord.status == "active",
                flight.flight_start <= as_of,
                flight.flight_end >= as_of,
            )
            .order_by(CampaignRecord.id, CampaignLineRecord.line_number)
        ).all()
        return [FlightDeliveryFigures(*row[:10], int(row[10]), int(row[11]), row[12]) for row in rows]
