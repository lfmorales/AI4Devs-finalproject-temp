"""The carry-over of a flight: volume a flight did not deliver, carried to the next flight of the same line.

The rules are those of campaign/carryover. A carry-over is written on the flight that receives it; it never changes
that flight's contracted volume, only its delivery target, the contracted volume plus the carry-over.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.exceptions import CarryoverError, TargetLineNotAdjustableError
from app.domain.value_objects.flight import FlightWindow


@dataclass(frozen=True)
class PreviousFlight:
    """The previous flight of a line, as a carry-over needs it: when it ends, what it had to deliver (its delivery
    target, with the carry-over it received itself) and what the line delivered inside its window as stored now. The
    volumes are in the unit of the line's delivery metric; `delivered` keeps its decimals."""

    flight_end: date
    delivery_target: int
    delivered: Decimal


def delivery_target(contracted: int, carryover: int) -> int:
    """What a flight has to deliver: its contracted volume plus the carry-over it received."""
    return contracted + carryover


def previous_flight_of(windows: Sequence[FlightWindow], receiving: FlightWindow) -> FlightWindow | None:
    """The flight of the same line with the latest window that ends before `receiving` starts, or None for the first."""
    earlier = [window for window in windows if window.flight_end < receiving.flight_start]
    return max(earlier, key=lambda window: window.flight_end, default=None)


def shortfall(previous: PreviousFlight) -> Decimal:
    """What the previous flight fell short of its delivery target, zero when it delivered the target or more."""
    return max(Decimal(0), Decimal(previous.delivery_target) - previous.delivered)


def validate_carryover(
    *,
    volume: int,
    reason: str,
    previous: PreviousFlight | None,
    receiving_month_closed: bool,
    as_of: date,
) -> None:
    """Refuse a carry-over that breaks a rule, reporting the first rule of the specification it breaks, in its order.

    `as_of` is D-1, the last day counted: a flight ending on it has ended. A volume of zero removes the carry-over and
    obeys the same rules, so it still needs a reason and is refused in a closed month.
    """
    if isinstance(volume, bool) or not isinstance(volume, int) or volume < 0:
        raise CarryoverError("invalid_carryover", "the volume of a carry-over is a whole number, zero or above")
    if not reason or not reason.strip():
        raise CarryoverError("invalid_carryover", "a carry-over needs a reason")
    if previous is None:
        raise CarryoverError("no_previous_flight", "the first flight of a line has no previous flight to carry from")
    if previous.flight_end > as_of:
        raise CarryoverError("previous_flight_not_ended", "the previous flight of the line has not ended yet")
    available = shortfall(previous)
    if Decimal(volume) > available:
        raise CarryoverError(
            "carryover_exceeds_shortfall", f"the previous flight fell short by {available.normalize():f}"
        )
    if receiving_month_closed:
        raise CarryoverError("month_closed", "the month of the flight that receives the carry-over is closed")


def validate_billable(*, is_target_line: bool, billable: bool, carryover: int, month_closed: bool) -> None:
    """Refuse a change of the billable flag that breaks a rule, reporting the first rule broken: a target line has no
    billable carry-over, true needs a carry-over to bill, and a closed month is not changed."""
    if is_target_line:
        raise TargetLineNotAdjustableError("a target line bills what its DSP reports: it has no billable carry-over")
    if billable and carryover == 0:
        raise CarryoverError("no_carryover", "the flight has no carry-over to bill")
    if month_closed:
        raise CarryoverError("month_closed", "the month of the flight is closed")
