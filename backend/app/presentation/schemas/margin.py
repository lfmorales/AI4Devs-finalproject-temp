from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer, model_validator

from app.domain.value_objects.closed_flight import ClosedDeliveryCheck
from app.domain.value_objects.margin import MarginTotals
from app.domain.value_objects.margin_report import FlightReport, FlightState, MarginReport
from app.domain.value_objects.platform_rate import PlatformRateLevel
from app.domain.value_objects.volume_commitment import VolumeCommitment
from app.presentation.schemas.quantity import IN_DELIVERY_METRIC, QuantityString


class ClosingRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class ClosingResponse(BaseModel):
    year: int
    month: int
    closed: int = Field(description="The flights this request froze.")
    already_closed: int = Field(description="The flights of the month frozen before this request.")
    closings: int = Field(
        description=(
            "The closing headers the month holds after this request: one per closing that froze a flight. More than "
            "one when a flight registered in a closed month was frozen by a later closing."
        )
    )


# Money and rates leave as decimal strings in plain notation, never as JSON numbers.
DecimalString = Annotated[Decimal, PlainSerializer(lambda value: format(value, "f"), return_type=str)]


class TotalsResponse(BaseModel):
    revenue: DecimalString
    contracted_revenue: DecimalString
    delivered_impressions: int = Field(description="The real impressions, always summed whatever the metric.")
    contracted_impressions: int | None = Field(
        description=f"The contracted volume, {IN_DELIVERY_METRIC}. Null when the totals mix metrics."
    )
    delivery_metric: str | None = Field(
        description="`impressions` or `ots`. Null when the totals mix metrics or hold no flight."
    )
    delivered: QuantityString | None = Field(
        description=f"The delivered volume, {IN_DELIVERY_METRIC}, four decimals. Null when the totals mix metrics."
    )
    media_cost: DecimalString
    rebate: DecimalString
    platform_cost: DecimalString
    margin: DecimalString
    provisional: bool
    flights_counted: int
    below_cost_count: int
    zero_sale_count: int
    margin_pct: DecimalString | None
    volume_commitment: VolumeCommitment | None = Field(
        description="The one commitment of the flights below, `committed` or `target`. Null when they mix both."
    )
    gross_revenue: DecimalString | None = Field(
        description="The exact sum of the gross of the target flights below, two decimals. Null when there is none."
    )
    gross_differs_count: int = Field(
        description="How many flights below have a gross more than 1 % away from the buyer's spend."
    )
    data_cost_count: int = Field(description="How many flights below report a third-party or audience data cost.")
    delivery_changed_count: int = Field(
        description="How many flights below carry `delivery_changed`. No amount of the totals changes because of them."
    )

    @classmethod
    def from_totals(cls, totals: MarginTotals) -> "TotalsResponse":
        return cls(
            revenue=totals.revenue, contracted_revenue=totals.contracted_revenue,
            delivered_impressions=totals.delivered_impressions, contracted_impressions=totals.contracted_impressions,
            delivery_metric=totals.delivery_metric, delivered=totals.delivered, media_cost=totals.media_cost,
            rebate=totals.rebate, platform_cost=totals.platform_cost, margin=totals.margin, provisional=totals.provisional,
            flights_counted=totals.flights_counted, below_cost_count=totals.below_cost_count,
            zero_sale_count=totals.zero_sale_count, margin_pct=totals.margin_pct,
            volume_commitment=totals.volume_commitment, gross_revenue=totals.gross_revenue,
            gross_differs_count=totals.gross_differs_count, data_cost_count=totals.data_cost_count,
            delivery_changed_count=totals.delivery_changed_count,
        )


_INFORMATIVE = (
    "Informative: the current margin uses the closing's rebate and rates with today's delivery; only the delivery "
    "changes, and no amount or total adds it."
)


class DeliveryChangeResponse(BaseModel):
    """A closed flight compared with the delivery stored now. Each difference is the current value less the frozen one."""

    delivered_difference: QuantityString = Field(
        description=f"The delivered volume, {IN_DELIVERY_METRIC}, four decimals."
    )
    delivered_impressions_difference: int = Field(description="The real impressions.")
    media_cost_difference: DecimalString = Field(description="The media cost, both rounded to the cent first.")
    reported_revenue_difference: DecimalString | None = Field(
        description="The revenue the DSP reports, both rounded to the cent first. Null for a committed flight."
    )
    buyer_spend_difference: DecimalString | None = Field(
        description="The buyer's spend, both rounded to the cent first. Null for a committed flight."
    )
    current_margin: DecimalString = Field(
        description=f"The margin the flight would have with the delivery stored now. {_INFORMATIVE}"
    )
    margin_difference: DecimalString = Field(description="`current_margin` less the frozen `margin`.")

    @classmethod
    def from_check(cls, check: ClosedDeliveryCheck) -> "DeliveryChangeResponse":
        return cls(
            delivered_difference=check.delivered_difference,
            delivered_impressions_difference=check.delivered_impressions_difference,
            media_cost_difference=check.media_cost_difference,
            reported_revenue_difference=check.reported_revenue_difference,
            buyer_spend_difference=check.buyer_spend_difference,
            current_margin=check.current_margin,
            margin_difference=check.margin_difference,
        )


class AppliedRatesResponse(BaseModel):
    platform_rate: DecimalString
    effective_rebate_rate: DecimalString
    rebate_step: int
    agency_exception: bool
    zero_reason: str | None
    source_year: int | None


class FlightMarginResponse(BaseModel):
    flight_id: int
    period_year: int
    period_month: int
    flight_start: date
    flight_end: date
    state: FlightState
    provisional: bool
    below_cost: bool
    zero_sale: bool
    revenue: DecimalString
    contracted_revenue: DecimalString
    accrued_days: int
    window_days: int
    delivered_impressions: int = Field(description="The real impressions inside the flight's window, whatever the metric.")
    contracted_impressions: int = Field(description=f"The flight's contracted volume, {IN_DELIVERY_METRIC}.")
    delivery_metric: str = Field(description="The unit the channel counts delivery in: `impressions` or `ots`.")
    delivered: QuantityString = Field(
        description=f"The line's delivery inside the flight's window, {IN_DELIVERY_METRIC}, four decimals."
    )
    media_cost: DecimalString
    rebate: DecimalString
    platform_cost: DecimalString
    margin: DecimalString
    margin_pct: DecimalString | None
    rates: AppliedRatesResponse
    volume_commitment: VolumeCommitment = Field(
        description=(
            "`committed`: revenue is the contracted volume times the CPM. `target`: revenue is what the DSP reports, "
            "and `contracted_revenue` is the sale of the target."
        )
    )
    gross_revenue: DecimalString | None = Field(
        description=(
            "A target flight's served impressions times the line's CPM, two decimals: the base of its rebate. Frozen "
            "with a closed month. Null for a committed flight."
        )
    )
    gross_differs_from_buyer_spend: bool = Field(
        description="A target flight whose gross differs from the buyer's spend by more than 1 %, or has no spend."
    )
    data_cost_reported: bool = Field(
        description="The DSP reports a third-party or audience data cost inside the flight's window; never subtracted."
    )
    delivery_changed: bool = Field(
        description=(
            "A closed flight whose delivery stored now moved from the one it was closed with: its margin by 1.00 € or "
            "more, or its delivered volume by 1 % or more. False for a flight that is not closed. No figure changes."
        )
    )
    delivery_change: DeliveryChangeResponse | None = Field(
        description=f"A closed flight's differences and current margin. Null until closed. {_INFORMATIVE}"
    )

    @classmethod
    def from_report(cls, report: FlightReport) -> "FlightMarginResponse":
        margin = report.margin
        assert margin.revenue is not None and margin.media_cost is not None and margin.rebate is not None
        assert margin.platform_cost is not None and margin.margin is not None
        assert margin.contracted_revenue is not None and margin.accrued_days is not None and margin.window_days is not None
        assert margin.delivered_impressions is not None and margin.contracted_impressions is not None
        assert margin.delivered is not None and margin.delivery_metric is not None
        assert margin.volume_commitment is not None
        rates = report.rates
        return cls(
            flight_id=report.flight_id, period_year=report.period_year, period_month=report.period_month,
            flight_start=report.flight_start, flight_end=report.flight_end, state=report.state,
            provisional=margin.provisional, below_cost=margin.below_cost, zero_sale=margin.zero_sale, revenue=margin.revenue,
            contracted_revenue=margin.contracted_revenue, accrued_days=margin.accrued_days, window_days=margin.window_days,
            delivered_impressions=margin.delivered_impressions, contracted_impressions=margin.contracted_impressions,
            delivery_metric=margin.delivery_metric, delivered=margin.delivered,
            media_cost=margin.media_cost, rebate=margin.rebate, platform_cost=margin.platform_cost,
            margin=margin.margin, margin_pct=margin.margin_pct,
            rates=AppliedRatesResponse(
                platform_rate=rates.platform_rate, effective_rebate_rate=rates.effective_rebate_rate,
                rebate_step=rates.rebate_step, agency_exception=rates.agency_exception,
                zero_reason=rates.zero_reason, source_year=rates.source_year,
            ),
            volume_commitment=margin.volume_commitment, gross_revenue=margin.gross_revenue,
            gross_differs_from_buyer_spend=margin.gross_differs_from_buyer_spend,
            data_cost_reported=margin.data_cost_reported,
            delivery_changed=margin.delivery_changed,
            delivery_change=(
                None if report.delivery_change is None else DeliveryChangeResponse.from_check(report.delivery_change)
            ),
        )


class LineMarginResponse(BaseModel):
    campaign_line_id: int
    line_number: int
    channel: str
    scope: str
    zero_sale: bool
    flights: list[FlightMarginResponse]
    totals: TotalsResponse


class CampaignMarginResponse(BaseModel):
    campaign_id: int
    name: str
    status: str
    zero_sale: bool
    lines: list[LineMarginResponse]
    totals: TotalsResponse


class MarginResponse(BaseModel):
    as_of: date
    campaigns: list[CampaignMarginResponse]
    totals: TotalsResponse

    @classmethod
    def from_report(cls, report: MarginReport) -> "MarginResponse":
        return cls(
            as_of=report.as_of,
            campaigns=[
                CampaignMarginResponse(
                    campaign_id=campaign.campaign_id, name=campaign.name, status=campaign.status,
                    zero_sale=campaign.totals.zero_sale,
                    lines=[
                        LineMarginResponse(
                            campaign_line_id=line.campaign_line_id, line_number=line.line_number,
                            channel=line.channel, scope=line.scope, zero_sale=line.totals.zero_sale,
                            flights=[FlightMarginResponse.from_report(flight) for flight in line.flights],
                            totals=TotalsResponse.from_totals(line.totals),
                        )
                        for line in campaign.lines
                    ],
                    totals=TotalsResponse.from_totals(campaign.totals),
                )
                for campaign in report.campaigns
            ],
            totals=TotalsResponse.from_totals(report.totals),
        )


def _refuse_json_numbers(value: object) -> object:
    """Amounts and rates are decimal strings: a JSON number may already have lost precision."""
    if isinstance(value, float):
        raise ValueError("send amounts as decimal strings, not as numbers")
    return value


StrictDecimal = Annotated[Decimal, BeforeValidator(_refuse_json_numbers)]


class BracketRequest(BaseModel):
    lower: StrictDecimal = Field(ge=0)
    upper: StrictDecimal | None = None
    rate: StrictDecimal = Field(ge=0)


class RebateScheduleRequest(BaseModel):
    holding_group_id: int = Field(ge=1)
    agency_id: int | None = Field(default=None, ge=1)
    channel_id: int | None = Field(default=None, ge=1)
    scope: Literal["national", "international"] | None = None
    valid_from: date
    valid_to: date | None = None
    brackets: list[BracketRequest]

    @model_validator(mode="after")
    def _validity_is_ordered(self) -> "RebateScheduleRequest":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not be before valid_from")
        return self


class BracketResponse(BaseModel):
    lower: DecimalString
    upper: DecimalString | None
    rate: DecimalString


class RebateScheduleResponse(BaseModel):
    id: int
    holding_group_id: int
    agency_id: int | None
    channel_id: int | None
    scope: str | None
    valid_from: date
    valid_to: date | None
    brackets: list[BracketResponse]


class PlatformRateRequest(BaseModel):
    level: PlatformRateLevel
    rate_per_thousand: StrictDecimal = Field(ge=0)
    campaign_line_id: int | None = Field(default=None, ge=1)
    agency_id: int | None = Field(default=None, ge=1)
    campaign_type_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _only_the_key_of_the_level(self) -> "PlatformRateRequest":
        given = {name for name, value in (
            ("campaign_line_id", self.campaign_line_id), ("agency_id", self.agency_id),
            ("campaign_type_id", self.campaign_type_id)) if value is not None}
        expected = {
            PlatformRateLevel.LINE: {"campaign_line_id"}, PlatformRateLevel.AGENCY: {"agency_id"},
            PlatformRateLevel.CAMPAIGN_TYPE: {"campaign_type_id"}, PlatformRateLevel.SYSTEM: set(),
        }[self.level]
        if given != expected:
            raise ValueError(f"level {self.level.value} takes exactly {sorted(expected) or 'no key'}")
        return self


class PlatformRateResponse(BaseModel):
    id: int
    level: PlatformRateLevel
    rate_per_thousand: DecimalString
    campaign_line_id: int | None
    agency_id: int | None
    campaign_type_id: int | None
    created_by: int | None
    created_at: datetime
