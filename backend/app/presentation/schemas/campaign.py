from pydantic import BaseModel, Field, model_validator
from datetime import date
from decimal import Decimal
from typing import Optional

from app.domain.exceptions import LineDatesInvalidError


class MonthlyVolumeRequest(BaseModel):
    """A volume the purchase order states for one calendar month of a line.

    Positivity is not checked here: the domain rejects it with its own business error.
    """

    year: int
    month: int = Field(..., ge=1, le=12)
    volume: int


class LineDatesRequest(BaseModel):
    """Optional dates of a line. They default to the campaign's and must be in order."""

    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @model_validator(mode="after")
    def _dates_are_in_order(self) -> "LineDatesRequest":
        # Raised as a domain error, not a ValueError, so it leaves as {"code","message"} and not as a field error.
        if self.start_date is not None and self.end_date is not None and self.start_date > self.end_date:
            raise LineDatesInvalidError("line start must be <= line end")
        return self


class CampaignLineCreateRequest(LineDatesRequest):
    """Request schema for campaign line creation."""

    dsp_id: int
    channel_id: int
    format_id: int
    scope: str = Field(..., description="national | international")
    market_description: str
    contracted_impressions: int = Field(..., gt=0)
    sale_cpm: Decimal = Field(..., ge=0, decimal_places=2)
    # Absent: the volume is split by days. Present: it must cover exactly the months the line runs in.
    monthly_volumes: Optional[list[MonthlyVolumeRequest]] = None


class CampaignCreateRequest(BaseModel):
    """Request schema for campaign registration."""

    name: str = Field(..., min_length=1, max_length=255)
    display_name: str = Field(..., min_length=1, max_length=255)
    agency_id: int
    advertiser_id: int
    campaign_type_id: int
    sector_id: int
    sales_rep_id: int
    start_date: date
    end_date: date
    order_reference: str = Field(..., min_length=1, max_length=255)
    order_received_on: date
    lines: list[CampaignLineCreateRequest] = Field(..., min_length=1)


class CampaignLineFlightResponse(BaseModel):
    """Response schema for a flight: the volume of a line in one calendar month."""

    campaign_period_id: int
    period_year: int
    period_month: int
    flight_start: date
    flight_end: date
    contracted_impressions: int


class CampaignLineResponse(BaseModel):
    """Response schema for campaign line. It has no period of its own: its flights do."""

    id: int
    line_number: int
    start_date: date
    end_date: date
    dsp_id: int
    channel_id: int
    format_id: int
    scope: str
    market_description: str
    contracted_impressions: int
    sale_cpm: Decimal
    currency: str = "EUR"
    flights: list[CampaignLineFlightResponse] = Field(default_factory=list)


class CampaignPeriodResponse(BaseModel):
    """Response schema for campaign period."""

    id: int
    campaign_id: int
    period_year: int
    period_month: int
    period_start: date
    period_end: date
    status: str


class CampaignResponse(BaseModel):
    """Response schema for campaign (with periods and lines)."""

    id: int
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
    status: str
    periods: list[CampaignPeriodResponse] = Field(default_factory=list)
    lines: list[CampaignLineResponse] = Field(default_factory=list)


class CampaignListResponse(BaseModel):
    """Response schema for campaign list."""

    id: int
    name: str
    display_name: str
    agency_id: int
    advertiser_id: int
    status: str
    start_date: date
    end_date: date
