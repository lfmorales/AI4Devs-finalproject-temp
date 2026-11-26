"""The billing of a month as Operations and Finance read it: per campaign its review state, per flight how its billing
was reached (finance/billing-report)."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.value_objects.billing import AdjustmentEntry, BillingBasis
from app.domain.value_objects.review import ReviewState


class BillingFlightState(StrEnum):
    """Where a flight stands in the billing read: the three states of the margin, and one for a flight not started."""

    NOT_STARTED = "not_started"
    RUNNING = "running"
    PENDING_CLOSE = "pending_close"
    CLOSED = "closed"


@dataclass(frozen=True)
class BillingFlight:
    """A flight of the month. Its billing, billable volume, basis and delivered volume are the margin read's, none for a
    flight that has not started. A closed flight's line attributes, carry-over and flag are its snapshot's; a flight
    closed before the billing was frozen has neither carry-over nor flag, and its delivery target is its contracted
    volume."""

    flight_id: int
    flight_start: date
    flight_end: date
    state: BillingFlightState
    delivery_metric: str
    contracted_impressions: int
    carryover: int | None
    carryover_billable: bool | None
    delivery_target: int
    delivered: Decimal | None
    billable: Decimal | None
    billing: Decimal | None
    billing_basis: BillingBasis | None
    sale_cpm: Decimal
    adjustment: AdjustmentEntry | None


@dataclass(frozen=True)
class BillingLine:
    campaign_line_id: int
    line_number: int
    flights: tuple[BillingFlight, ...]


@dataclass(frozen=True)
class BillingCampaign:
    """A campaign with flights in the month, its review state and who wrote its latest review event, and when."""

    campaign_id: int
    name: str
    agency: str
    advertiser: str
    review_state: ReviewState
    review_set_by: int | None
    review_set_at: datetime | None
    lines: tuple[BillingLine, ...]


@dataclass(frozen=True)
class BillingReport:
    year: int
    month: int
    as_of: date
    campaigns: tuple[BillingCampaign, ...]
