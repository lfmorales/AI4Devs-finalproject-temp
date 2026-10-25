from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from app.domain.value_objects.contracted_volume import ContractedVolume


@dataclass
class CampaignPeriod:
    """Campaign period: one calendar month."""

    period_year: int
    period_month: int
    period_start: date
    period_end: date
    id: Optional[int] = None
    campaign_id: Optional[int] = None
    status: str = "open"


@dataclass
class CampaignLineFlight:
    """The volume of one campaign line in one calendar month, over the days the two share."""

    period_year: int
    period_month: int
    flight_start: date
    flight_end: date
    contracted_impressions: int
    campaign_period_id: Optional[int] = None
    id: Optional[int] = None


@dataclass
class CampaignLine:
    """Campaign execution spec for a DSP and channel, hanging from the campaign with its own dates.

    The months it runs in are its flights; the line holds the total volume and the price.
    """

    id: Optional[int]
    purchase_order_version_id: Optional[int]
    dsp_id: int
    channel_id: int
    format_id: int
    scope: str  # 'national' | 'international'
    market_description: str
    volume: ContractedVolume
    currency: str = "EUR"
    campaign_id: Optional[int] = None
    line_number: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    flights: list[CampaignLineFlight] = field(default_factory=list)
    # Transitional: the column is still mandatory and is filled from the first flight. Removed with the repository.
    campaign_period_id: Optional[int] = None

    def __post_init__(self):
        """Validate scope enumeration."""
        valid_scopes = {"national", "international"}
        if self.scope not in valid_scopes:
            raise ValueError(f"scope must be one of {valid_scopes}, got '{self.scope}'")


@dataclass
class Campaign:
    """
    Campaign: execution of a contract.

    Aggregates periods and lines that together define what gets delivered.
    Each campaign line is assigned a period and a DSP.
    """

    id: Optional[int]
    name: str
    display_name: str
    agency_id: int
    advertiser_id: int
    campaign_type_id: int
    sector_id: int
    sales_rep_id: int
    purchase_order_id: Optional[int]
    start_date: date
    end_date: date
    status: str = "active"
    periods: list[CampaignPeriod] = field(default_factory=list)
    lines: list[CampaignLine] = field(default_factory=list)

    def validate(self) -> None:
        """Validate campaign invariants."""
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")

        if self.status not in {"active", "inactive"}:
            raise ValueError(f"Invalid campaign status: {self.status}")
