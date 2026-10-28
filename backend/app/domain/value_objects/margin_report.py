from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.domain.value_objects.margin import FlightMargin, MarginTotals


class FlightState(StrEnum):
    """Where a flight stands: frozen, ended but not yet frozen, or still running. A flight not started has none."""

    CLOSED = "closed"
    PENDING_CLOSE = "pending_close"
    RUNNING = "running"


@dataclass(frozen=True)
class FrozenRates:
    """What closing froze for a flight; a closed flight is read from these and never priced again."""

    rebate_amount: Decimal
    platform_rate: Decimal
    effective_rate: Decimal
    ladder_step: int
    agency_exception: bool
    zero_reason: str | None
    source_year: int | None
    position_before: Decimal
    position_after: Decimal


@dataclass(frozen=True)
class AppliedRates:
    """The rates a flight's figures were computed with, whether frozen or in force."""

    platform_rate: Decimal
    effective_rebate_rate: Decimal
    rebate_step: int
    agency_exception: bool
    zero_reason: str | None
    source_year: int | None


@dataclass(frozen=True)
class FlightReport:
    flight_id: int
    period_year: int
    period_month: int
    flight_start: date
    flight_end: date
    state: FlightState
    margin: FlightMargin
    rates: AppliedRates


@dataclass(frozen=True)
class LineReport:
    campaign_line_id: int
    line_number: int
    channel: str
    scope: str
    flights: tuple[FlightReport, ...]
    totals: MarginTotals


@dataclass(frozen=True)
class CampaignReport:
    campaign_id: int
    name: str
    status: str
    agency_id: int
    lines: tuple[LineReport, ...]
    totals: MarginTotals


@dataclass(frozen=True)
class MarginReport:
    as_of: date
    campaigns: tuple[CampaignReport, ...]
    totals: MarginTotals
