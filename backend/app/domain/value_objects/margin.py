from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class FlightStatus(StrEnum):
    CLOSED = "closed"
    RUNNING = "running"
    NOT_STARTED = "not_started"


def _require_decimal(name: str, value: object) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, not {type(value).__name__}")


@dataclass(frozen=True)
class FlightEconomics:
    """Everything the margin of one flight is computed from.

    `rebate_amount` is the exact rebate of the whole flight, unrounded: the bracket engine produces it.
    `media_cost` and `delivered_impressions` are the line's delivery inside the flight's window.
    `platform_rate` is euros per thousand delivered impressions.
    """

    flight_start: date
    flight_end: date
    contracted_impressions: int
    sale_cpm: Decimal
    delivered_impressions: int
    media_cost: Decimal
    rebate_amount: Decimal
    platform_rate: Decimal

    def __post_init__(self) -> None:
        if self.flight_start > self.flight_end:
            raise ValueError("flight_start must be <= flight_end")
        for name in ("sale_cpm", "media_cost", "rebate_amount", "platform_rate"):
            _require_decimal(name, getattr(self, name))

    @property
    def total_days(self) -> int:
        return (self.flight_end - self.flight_start).days + 1


@dataclass(frozen=True)
class FlightMargin:
    """The economics of one flight. A flight that has not started has a status and no amounts."""

    status: FlightStatus
    revenue: Decimal | None
    media_cost: Decimal | None
    rebate: Decimal | None
    platform_cost: Decimal | None
    margin: Decimal | None
    provisional: bool
    below_cost: bool
    # Sin venta: the line has a sale CPM of 0.00, so the flight has no revenue and no rebate but still has cost.
    zero_sale: bool = False


@dataclass(frozen=True)
class MarginTotals:
    """The exact sum of the amounts of a set of flights (a line) or of lines (a campaign).

    A below-cost flight stays in every amount; it is only counted. A flight that has not started is not
    added, only counted.
    """

    revenue: Decimal
    media_cost: Decimal
    rebate: Decimal
    platform_cost: Decimal
    margin: Decimal
    provisional: bool
    flights_counted: int
    below_cost_count: int
    not_started_count: int
    zero_sale_count: int = 0

    @property
    def zero_sale(self) -> bool:
        """A line carries it when one of its flights does, a campaign when one of its lines does."""
        return self.zero_sale_count > 0


@dataclass(frozen=True)
class WindowDelivery:
    """What a line delivered inside one flight's window: the inputs of its media cost and platform cost."""

    impressions: int
    media_cost: Decimal
