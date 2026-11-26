from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.services.pacing import PacingResult
from app.domain.value_objects.volume_commitment import VolumeCommitment


@dataclass(frozen=True)
class FlightDeliveryFigures:
    """One running flight with the figures the daily status is calculated from. Carries no cost."""

    campaign_id: int
    campaign_name: str
    agency_id: int
    agency_name: str
    line_number: int
    campaign_period_id: int
    period_year: int
    period_month: int
    flight_start: date
    flight_end: date
    contracted_impressions: int
    # The unit the channel counts delivery in: "impressions" or "ots".
    delivery_metric: str
    # The line's delivery in that unit from flight_start up to the day being evaluated.
    delivered: Decimal
    # The line's real impressions over the same days, whatever the metric.
    delivered_impressions: int
    # The latest delivery date of any line of the campaign; None when the campaign has no delivery at all.
    campaign_latest_delivery_date: date | None
    # Declared on the line: a target volume is only flagged when delivery falls behind it.
    volume_commitment: VolumeCommitment
    # The volume carried to this flight from the previous flight of its line, in the unit of `delivery_metric`: the
    # pacing is measured against the contracted volume plus it. Neither its reason nor its billable flag is read here.
    carryover: int
    flight_id: int


@dataclass(frozen=True)
class CampaignStatusRow:
    """One row of the daily status: a running flight with its pacing and the flags. Carries no cost."""

    campaign_id: int
    campaign_name: str
    agency_id: int
    agency_name: str
    line_number: int
    campaign_period_id: int
    period_year: int
    period_month: int
    flight_start: date
    flight_end: date
    contracted_impressions: int
    delivery_metric: str
    delivered: Decimal
    delivered_impressions: int
    delivery_ratio: float | None
    pacing: PacingResult
    pacing_flag: bool
    # Belongs to the campaign and repeats on every row of it.
    missing_data_flag: bool
    volume_commitment: VolumeCommitment
    carryover: int
    # The contracted volume plus the carry-over: what the pacing and the ratio are measured against.
    delivery_target: int
    flight_id: int
