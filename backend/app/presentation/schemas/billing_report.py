from datetime import date, datetime

from pydantic import BaseModel, Field

from app.domain.value_objects.billing import AdjustmentEntry, BillingBasis
from app.domain.value_objects.billing_report import (
    BillingCampaign,
    BillingFlight,
    BillingFlightState,
    BillingLine,
    BillingReport,
)
from app.domain.value_objects.review import ReviewState
from app.presentation.schemas.billing_adjustments import MoneyString
from app.presentation.schemas.margin import DecimalString
from app.presentation.schemas.quantity import IN_DELIVERY_METRIC, QuantityString


class BillingAdjustmentInForce(BaseModel):
    """The adjustment that prices the flight: the latest, or the one its closing froze."""

    basis: BillingBasis
    amount: MoneyString | None = Field(description="Only with `custom`, two decimals.")
    reason: str
    created_by: int = Field(description="The user who made it.")
    created_at: datetime

    @classmethod
    def from_entry(cls, entry: AdjustmentEntry) -> "BillingAdjustmentInForce":
        return cls(
            basis=entry.adjustment.basis, amount=entry.adjustment.amount, reason=entry.reason,
            created_by=entry.created_by, created_at=entry.created_at,
        )


class BillingFlightResponse(BaseModel):
    flight_id: int
    flight_start: date
    flight_end: date
    state: BillingFlightState
    delivery_metric: str = Field(description="The unit the channel counts delivery in: `impressions` or `ots`.")
    contracted_impressions: int = Field(description=f"The flight's contracted volume, {IN_DELIVERY_METRIC}.")
    carryover: int | None = Field(
        description=f"The volume carried to the flight, {IN_DELIVERY_METRIC}. Null for a flight closed before the "
        "billing was frozen."
    )
    carryover_billable: bool | None = Field(
        description="Whether the carry-over raises the cap of the billing. Null for a flight closed before the billing "
        "was frozen."
    )
    delivery_target: int = Field(description=f"The contracted volume plus the carry-over, {IN_DELIVERY_METRIC}.")
    delivered: QuantityString | None = Field(
        description=f"As `GET /margin` gives it, {IN_DELIVERY_METRIC}, four decimals. Null for a flight not started."
    )
    billable: QuantityString | None = Field(
        description="As `GET /margin` gives it. Null for a flight not started, a target flight and a custom billing."
    )
    billing: DecimalString | None = Field(
        description="What the flight bills, two decimals: `GET /margin`'s `revenue`. Null for a flight not started."
    )
    billing_basis: BillingBasis | None = Field(description="As `GET /margin` gives it. Null for a flight not started.")
    sale_cpm: DecimalString = Field(description="The line's sale CPM; a closed flight's as its closing froze it.")
    adjustment: BillingAdjustmentInForce | None

    @classmethod
    def from_flight(cls, flight: BillingFlight) -> "BillingFlightResponse":
        return cls(
            flight_id=flight.flight_id, flight_start=flight.flight_start, flight_end=flight.flight_end,
            state=flight.state, delivery_metric=flight.delivery_metric,
            contracted_impressions=flight.contracted_impressions, carryover=flight.carryover,
            carryover_billable=flight.carryover_billable, delivery_target=flight.delivery_target,
            delivered=flight.delivered, billable=flight.billable, billing=flight.billing,
            billing_basis=flight.billing_basis, sale_cpm=flight.sale_cpm,
            adjustment=None if flight.adjustment is None else BillingAdjustmentInForce.from_entry(flight.adjustment),
        )


class BillingLineResponse(BaseModel):
    campaign_line_id: int
    line_number: int
    flights: list[BillingFlightResponse]

    @classmethod
    def from_line(cls, line: BillingLine) -> "BillingLineResponse":
        return cls(
            campaign_line_id=line.campaign_line_id, line_number=line.line_number,
            flights=[BillingFlightResponse.from_flight(flight) for flight in line.flights],
        )


class BillingCampaignResponse(BaseModel):
    campaign_id: int
    name: str
    agency: str
    advertiser: str
    review_state: ReviewState = Field(description="As of D-1: `in_progress`, `pending_review`, `reviewed` or `closed`.")
    review_set_by: int | None = Field(description="Who wrote the campaign's latest review event in the month.")
    review_set_at: datetime | None = Field(description="When that event was written.")
    lines: list[BillingLineResponse]

    @classmethod
    def from_campaign(cls, campaign: BillingCampaign) -> "BillingCampaignResponse":
        return cls(
            campaign_id=campaign.campaign_id, name=campaign.name, agency=campaign.agency,
            advertiser=campaign.advertiser, review_state=campaign.review_state,
            review_set_by=campaign.review_set_by, review_set_at=campaign.review_set_at,
            lines=[BillingLineResponse.from_line(line) for line in campaign.lines],
        )


class BillingResponse(BaseModel):
    """The billing of a month. Only operations and finance read it."""

    year: int
    month: int
    as_of: date = Field(description="D-1, the last day counted.")
    campaigns: list[BillingCampaignResponse]

    @classmethod
    def from_report(cls, report: BillingReport) -> "BillingResponse":
        return cls(
            year=report.year, month=report.month, as_of=report.as_of,
            campaigns=[BillingCampaignResponse.from_campaign(campaign) for campaign in report.campaigns],
        )
