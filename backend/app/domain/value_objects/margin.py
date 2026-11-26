from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.domain.value_objects.volume_commitment import VolumeCommitment


_ONE_HUNDRED = Decimal(100)
_HUNDREDTH = Decimal("0.01")


def margin_percentage(margin: Decimal | None, revenue: Decimal | None) -> Decimal | None:
    """Margin over revenue in percentage points, two decimals, half up; None when there is no revenue to divide by."""
    if margin is None or revenue is None or revenue == 0:
        return None
    return (margin * _ONE_HUNDRED / revenue).quantize(_HUNDREDTH, rounding=ROUND_HALF_UP)


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
    `platform_rate` is euros per thousand delivered impressions: the platform cost is on the real impressions
    whichever the delivery metric. `delivered` is the delivery in the unit of the metric (`delivery_metric`: impressions or
    OTS, with decimals). The revenue of a committed flight reads neither: it is the contracted volume's.

    `volume_commitment` is declared on the line. A target flight earns `reported_revenue`, what its DSP reports inside the
    window, and its `buyer_spend` is only compared with its gross. `data_cost` is the third-party and audience data costs
    inside the window, summed: only its presence is flagged, it is never subtracted. `gross_revenue` is the gross frozen
    when the flight's month was closed; None computes it from the served impressions, as for every flight not closed.
    """

    flight_start: date
    flight_end: date
    contracted_impressions: int
    sale_cpm: Decimal
    delivered_impressions: int
    media_cost: Decimal
    rebate_amount: Decimal
    platform_rate: Decimal
    delivery_metric: str
    delivered: Decimal
    volume_commitment: VolumeCommitment
    reported_revenue: Decimal
    buyer_spend: Decimal
    data_cost: Decimal
    gross_revenue: Decimal | None

    def __post_init__(self) -> None:
        if self.flight_start > self.flight_end:
            raise ValueError("flight_start must be <= flight_end")
        for name in (
            "sale_cpm", "media_cost", "rebate_amount", "platform_rate", "delivered", "reported_revenue", "buyer_spend",
            "data_cost",
        ):
            _require_decimal(name, getattr(self, name))
        if self.gross_revenue is not None:
            _require_decimal("gross_revenue", self.gross_revenue)

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
    # The sale of the whole flight, the days counted up to `as_of` and the days of the whole window. A running flight's
    # `revenue` is the accrued part of `contracted_revenue`; a closed one has them equal. None when not started.
    contracted_revenue: Decimal | None = None
    accrued_days: int | None = None
    window_days: int | None = None
    # The line's deliveries inside the flight's window and the flight's contracted volume. None when not started.
    delivered_impressions: int | None = None
    contracted_impressions: int | None = None
    # The same delivery in the unit of the metric, and that unit. The metric is known before the flight starts;
    # `delivered` is None until then.
    delivered: Decimal | None = None
    delivery_metric: str | None = None
    # Known before the flight starts, like the metric. Only a target flight has a gross: its served impressions times
    # the sale CPM, the base of its rebate. None for a committed flight and before the flight starts.
    volume_commitment: VolumeCommitment | None = None
    gross_revenue: Decimal | None = None
    # A target flight whose gross is more than GROSS_TOLERANCE away from the buyer's spend, or has no spend.
    gross_differs_from_buyer_spend: bool = False
    # Any flight with a third-party or audience data cost inside its window; no amount changes.
    data_cost_reported: bool = False
    # A closed flight whose delivery stored now moved beyond the tolerances from the one it was closed with; no amount
    # changes. Always false for a flight that is not closed.
    delivery_changed: bool = False

    @property
    def margin_pct(self) -> Decimal | None:
        return margin_percentage(self.margin, self.revenue)


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
    contracted_revenue: Decimal = Decimal("0.00")
    delivered_impressions: int = 0
    # `contracted_impressions` and `delivered` are in the unit of `delivery_metric`. Where the flights counted
    # in two metrics (a grand total over DOOH and CTV campaigns) they cannot be added: all three are None. The real
    # `delivered_impressions` is always a count of impressions and is always summed. No flights: metric None, zeros.
    contracted_impressions: int | None = 0
    delivered: Decimal | None = Decimal(0)
    delivery_metric: str | None = None
    # The exact sum of the gross of the target flights below; None when there is none.
    gross_revenue: Decimal | None = None
    # How many flights below carry each flag.
    gross_differs_count: int = 0
    data_cost_count: int = 0
    delivery_changed_count: int = 0
    # The one commitment of the flights or lines below; None when they disagree, or when there are none.
    volume_commitment: VolumeCommitment | None = None

    @property
    def zero_sale(self) -> bool:
        """A line carries it when one of its flights does, a campaign when one of its lines does."""
        return self.zero_sale_count > 0

    @property
    def margin_pct(self) -> Decimal | None:
        return margin_percentage(self.margin, self.revenue)


@dataclass(frozen=True)
class WindowDelivery:
    """What a line delivered inside one flight's window: the inputs of its media cost and platform cost.

    And what its DSP reported besides: the revenue a target flight earns, the buyer's spend its gross is compared with
    and the data costs, summed, whose presence is flagged.
    """

    impressions: int
    media_cost: Decimal
    # The delivery in the unit of the metric: its OTS when the line counts in OTS, its impressions otherwise.
    delivered: Decimal
    reported_revenue: Decimal
    buyer_spend: Decimal
    data_cost: Decimal
