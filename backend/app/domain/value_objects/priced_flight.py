from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.domain.value_objects.margin import FlightMargin
from app.domain.value_objects.margin_report import FrozenRates
from app.domain.value_objects.platform_rate import ResolvedPlatformRate
from app.domain.value_objects.rebate import FlightRebate


@dataclass(frozen=True)
class FlightFacts:
    """Everything stored about a flight that its margin is computed from.

    `channel` is the channel's name, the value the rebate rules key on; `channel_id` is kept to persist it.
    `delivered_impressions` and `media_cost` are the line's delivery inside the flight's window.
    """

    flight_id: int
    campaign_line_id: int
    campaign_id: int
    flight_start: date
    flight_end: date
    group_id: int
    agency_id: int
    campaign_type_id: int
    channel: str
    channel_id: int
    scope: str
    contracted_impressions: int
    sale_cpm: Decimal
    delivered_impressions: int
    media_cost: Decimal


@dataclass(frozen=True)
class PlatformRates:
    """The platform rates in force: the system value plus the overrides of each level, by their key."""

    system: Decimal
    by_campaign_type: Mapping[int, Decimal] = field(default_factory=dict)
    by_agency: Mapping[int, Decimal] = field(default_factory=dict)
    by_line: Mapping[int, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class PricedFlight:
    """A flight with the rebate, the platform rate and the margin it was priced with."""

    facts: FlightFacts
    rebate: FlightRebate
    platform: ResolvedPlatformRate
    margin: FlightMargin


@dataclass(frozen=True)
class ReadFlight:
    """A flight as the margin read needs it: its facts, where it sits and, if closed, what was frozen."""

    facts: FlightFacts
    campaign_name: str
    campaign_status: str
    line_number: int
    period_year: int
    period_month: int
    frozen: FrozenRates | None
