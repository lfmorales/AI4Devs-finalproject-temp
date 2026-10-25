from datetime import date

from pydantic import BaseModel

from app.domain.entities.campaign_status import CampaignStatusRow
from app.domain.services.pacing import PacingStatus


class NamedReference(BaseModel):
    id: int
    name: str


class FlightWindowResponse(BaseModel):
    campaign_period_id: int
    year: int
    month: int
    start: date
    end: date


class PacingResponse(BaseModel):
    expected_impressions: float
    # Signed (delivered - expected) / expected; None while nothing is expected yet.
    deviation: float | None
    days_remaining: int
    status: PacingStatus


class CampaignStatusResponse(BaseModel):
    """One running flight. Deliberately has no cost or margin field: the daily status is open to business."""

    campaign: NamedReference
    agency: NamedReference
    line_number: int
    flight: FlightWindowResponse
    contracted_impressions: int
    delivered_impressions: int
    delivery_ratio: float | None
    pacing: PacingResponse
    pacing_flag: bool
    missing_data_flag: bool

    @classmethod
    def from_row(cls, row: CampaignStatusRow) -> "CampaignStatusResponse":
        return cls(
            campaign=NamedReference(id=row.campaign_id, name=row.campaign_name),
            agency=NamedReference(id=row.agency_id, name=row.agency_name),
            line_number=row.line_number,
            flight=FlightWindowResponse(
                campaign_period_id=row.campaign_period_id, year=row.period_year, month=row.period_month,
                start=row.flight_start, end=row.flight_end,
            ),
            contracted_impressions=row.contracted_impressions,
            delivered_impressions=row.delivered_impressions,
            delivery_ratio=row.delivery_ratio,
            pacing=PacingResponse(
                expected_impressions=float(row.pacing.expected_impressions),
                deviation=None if row.pacing.deviation is None else float(row.pacing.deviation),
                days_remaining=row.pacing.days_remaining,
                status=row.pacing.status,
            ),
            pacing_flag=row.pacing_flag,
            missing_data_flag=row.missing_data_flag,
        )
