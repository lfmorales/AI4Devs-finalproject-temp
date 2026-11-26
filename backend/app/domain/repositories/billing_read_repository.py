from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.domain.services.monthly_review import FlightCounts
from app.domain.value_objects.billing import AdjustmentEntry
from app.domain.value_objects.review import ReviewKind


@dataclass(frozen=True)
class MonthCampaignRow:
    """A campaign with flights in the month: its names, its flights' counts as of D-1 and its latest review event."""

    campaign_id: int
    name: str
    agency: str
    advertiser: str
    counts: FlightCounts
    latest_kind: ReviewKind | None
    latest_by: int | None
    latest_at: datetime | None


@dataclass(frozen=True)
class MonthFlightRow:
    """A flight of the month as stored: a closed flight's contracted volume, metric, sale CPM, carry-over and flag are
    its snapshot's (none of the last two for a snapshot written before the billing was frozen), and its adjustment the
    one it froze; any other flight's are the line's and the flight's now, and its adjustment the one in force."""

    flight_id: int
    campaign_id: int
    campaign_line_id: int
    line_number: int
    flight_start: date
    flight_end: date
    contracted_impressions: int
    delivery_metric: str
    sale_cpm: Decimal
    carryover: int | None
    carryover_billable: bool | None
    adjustment: AdjustmentEntry | None


class BillingReadRepository(ABC):
    """Reads what the billing of a month adds to the margin: names, review events and adjustments. Writes nothing."""

    @abstractmethod
    def campaign_exists(self, campaign_id: int) -> bool: ...

    @abstractmethod
    def month_campaigns(
        self, year: int, month: int, as_of: date, campaign_id: int | None = None
    ) -> list[MonthCampaignRow]:
        """Every campaign with flights in the month (its campaign period), by name and then id."""

    @abstractmethod
    def month_flights(self, year: int, month: int, campaign_id: int | None = None) -> list[MonthFlightRow]:
        """Every flight of the month's campaign periods, by line number and then flight start."""
