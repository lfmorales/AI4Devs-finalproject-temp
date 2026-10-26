from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer

from app.domain.value_objects.margin import MarginTotals
from app.domain.value_objects.margin_report import FlightReport, FlightState, MarginReport


class ClosingRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class ClosingResponse(BaseModel):
    year: int
    month: int
    closed: int
    already_closed: int


# Money and rates leave as decimal strings in plain notation, never as JSON numbers.
DecimalString = Annotated[Decimal, PlainSerializer(lambda value: format(value, "f"), return_type=str)]


class TotalsResponse(BaseModel):
    revenue: DecimalString
    media_cost: DecimalString
    rebate: DecimalString
    platform_cost: DecimalString
    margin: DecimalString
    provisional: bool
    flights_counted: int
    below_cost_count: int

    @classmethod
    def from_totals(cls, totals: MarginTotals) -> "TotalsResponse":
        return cls(
            revenue=totals.revenue, media_cost=totals.media_cost, rebate=totals.rebate,
            platform_cost=totals.platform_cost, margin=totals.margin, provisional=totals.provisional,
            flights_counted=totals.flights_counted, below_cost_count=totals.below_cost_count,
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
    revenue: DecimalString
    media_cost: DecimalString
    rebate: DecimalString
    platform_cost: DecimalString
    margin: DecimalString
    rates: AppliedRatesResponse

    @classmethod
    def from_report(cls, report: FlightReport) -> "FlightMarginResponse":
        margin = report.margin
        assert margin.revenue is not None and margin.media_cost is not None and margin.rebate is not None
        assert margin.platform_cost is not None and margin.margin is not None
        rates = report.rates
        return cls(
            flight_id=report.flight_id, period_year=report.period_year, period_month=report.period_month,
            flight_start=report.flight_start, flight_end=report.flight_end, state=report.state,
            provisional=margin.provisional, below_cost=margin.below_cost, revenue=margin.revenue,
            media_cost=margin.media_cost, rebate=margin.rebate, platform_cost=margin.platform_cost,
            margin=margin.margin,
            rates=AppliedRatesResponse(
                platform_rate=rates.platform_rate, effective_rebate_rate=rates.effective_rebate_rate,
                rebate_step=rates.rebate_step, agency_exception=rates.agency_exception,
                zero_reason=rates.zero_reason, source_year=rates.source_year,
            ),
        )


class LineMarginResponse(BaseModel):
    campaign_line_id: int
    line_number: int
    channel: str
    scope: str
    flights: list[FlightMarginResponse]
    totals: TotalsResponse


class CampaignMarginResponse(BaseModel):
    campaign_id: int
    name: str
    status: str
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
                    lines=[
                        LineMarginResponse(
                            campaign_line_id=line.campaign_line_id, line_number=line.line_number,
                            channel=line.channel, scope=line.scope,
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
