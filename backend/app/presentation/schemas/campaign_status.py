from datetime import date

from pydantic import BaseModel, Field

from app.domain.entities.campaign_status import CampaignStatusRow
from app.domain.services.pacing import PacingStatus
from app.domain.value_objects.volume_commitment import VolumeCommitment
from app.presentation.schemas.quantity import IN_DELIVERY_METRIC, QuantityString


class NamedReference(BaseModel):
    id: int
    name: str


class FlightWindowResponse(BaseModel):
    id: int = Field(description="The flight: the row of the line in this month, which receives a carry-over.")
    campaign_period_id: int
    year: int
    month: int
    start: date
    end: date


class PacingResponse(BaseModel):
    expected_impressions: float = Field(
        description=f"The volume a linear delivery would have reached, {IN_DELIVERY_METRIC}."
    )
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
    contracted_impressions: int = Field(
        description=f"The flight's contracted volume, {IN_DELIVERY_METRIC}. It never includes the carry-over."
    )
    carryover: int = Field(
        description=f"The volume carried to this flight from the previous flight of its line, {IN_DELIVERY_METRIC}; 0 when none."
    )
    delivery_target: int = Field(
        description=f"The contracted volume plus the carry-over, {IN_DELIVERY_METRIC}: what the pacing and the ratio use."
    )
    delivery_metric: str = Field(description="The unit the channel counts delivery in: `impressions` or `ots`.")
    delivered: QuantityString = Field(
        description=f"The line's delivery from the flight's start to D-1, {IN_DELIVERY_METRIC}, four decimals."
    )
    delivered_impressions: int = Field(description="The real impressions over the same days, whatever the metric.")
    delivery_ratio: float | None
    pacing: PacingResponse
    pacing_flag: bool
    missing_data_flag: bool
    volume_commitment: VolumeCommitment = Field(
        description=(
            "What the line's volume means: `committed`, a volume the buyer committed to, or `target`, an objective the "
            "buyer may exceed, whose pacing is flagged only below it. Not a cost or margin figure."
        )
    )

    @classmethod
    def from_row(cls, row: CampaignStatusRow) -> "CampaignStatusResponse":
        return cls(
            campaign=NamedReference(id=row.campaign_id, name=row.campaign_name),
            agency=NamedReference(id=row.agency_id, name=row.agency_name),
            line_number=row.line_number,
            flight=FlightWindowResponse(
                id=row.flight_id, campaign_period_id=row.campaign_period_id, year=row.period_year, month=row.period_month,
                start=row.flight_start, end=row.flight_end,
            ),
            contracted_impressions=row.contracted_impressions,
            carryover=row.carryover,
            delivery_target=row.delivery_target,
            delivery_metric=row.delivery_metric,
            delivered=row.delivered,
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
            volume_commitment=row.volume_commitment,
        )
