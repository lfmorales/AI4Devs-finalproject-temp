from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.domain.value_objects.billing import BillingAdjustment
from app.domain.value_objects.margin import FlightMargin
from app.domain.value_objects.margin_report import FrozenRates
from app.domain.value_objects.platform_rate import ResolvedPlatformRate
from app.domain.value_objects.rebate import FlightRebate
from app.domain.value_objects.volume_commitment import VolumeCommitment


@dataclass(frozen=True)
class FlightFacts:
    """Everything stored about a flight that its margin is computed from.

    `channel` is the channel's name, the value the rebate rules key on; `channel_id` is kept to persist it.
    `delivered_impressions` and `media_cost` are the line's delivery inside the flight's window. `delivered` is that
    delivery in the unit of the channel (`delivery_metric`: impressions or OTS), with decimals.
    `volume_commitment` is declared on the line; `reported_revenue`, `buyer_spend` and `data_cost` (third-party and
    audience summed) are what the DSP reported inside the window. `carryover` is the volume carried to the flight from
    the previous flight of its line, in the unit of `delivery_metric`, and `carryover_billable` whether it raises the
    cap of the billing; `adjustment` is the billing adjustment in force, if any, and `adjustment_id` the stored entry it
    was read from, which the closing freezes with it.
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
    delivery_metric: str
    delivered: Decimal
    volume_commitment: VolumeCommitment
    reported_revenue: Decimal
    buyer_spend: Decimal
    data_cost: Decimal
    carryover: int
    carryover_billable: bool
    adjustment: BillingAdjustment | None
    adjustment_id: int | None


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
