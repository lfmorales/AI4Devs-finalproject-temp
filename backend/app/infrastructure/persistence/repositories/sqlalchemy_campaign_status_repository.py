from datetime import date

from decimal import Decimal

from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.orm import Session, aliased

from app.domain.entities.campaign_status import FlightDeliveryFigures
from app.domain.repositories.campaign_status_repository import CampaignStatusRepository
from app.domain.value_objects.volume_commitment import VolumeCommitment
from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
)
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord
from app.infrastructure.persistence.models.masters import AgencyRecord, ChannelRecord
from app.infrastructure.persistence.repositories.delivered_volume import delivered_in_channel_metric


class SqlAlchemyCampaignStatusRepository(CampaignStatusRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_running_flights(self, as_of: date) -> list[FlightDeliveryFigures]:
        flight = CampaignLinePeriodRecord
        # The aggregates run in the database over the indexed (line, date) pair: no delivery row is fetched.
        # The delivered volume is summed in the unit the line's channel counts in, as a four-decimal number.
        delivered = (
            select(cast(func.coalesce(func.sum(delivered_in_channel_metric()), 0), Numeric(18, 4)))
            .where(
                DailyDeliveryRecord.campaign_line_id == flight.campaign_line_id,
                DailyDeliveryRecord.delivery_date.between(flight.flight_start, as_of),
            )
            .scalar_subquery()
        )
        delivered_impressions = (
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
                ChannelRecord.delivery_metric, delivered, delivered_impressions, latest_of_campaign,
                CampaignLineRecord.volume_commitment,
            )
            .select_from(flight)
            .join(CampaignLineRecord, CampaignLineRecord.id == flight.campaign_line_id)
            .join(ChannelRecord, ChannelRecord.id == CampaignLineRecord.channel_id)
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
        return [
            FlightDeliveryFigures(
                *row[:10], contracted_impressions=int(row[10]), delivery_metric=row[11],
                delivered=Decimal(row[12]), delivered_impressions=int(row[13]),
                campaign_latest_delivery_date=row[14], volume_commitment=VolumeCommitment(row[15]),
            )
            for row in rows
        ]
