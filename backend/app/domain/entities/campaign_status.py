from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.services.pacing import PacingResult


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
