from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import IntEnum, StrEnum

from app.domain.exceptions import RebateRuleError


class LadderStep(IntEnum):
    """The step of the resolution ladder that produced a schedule. Step 7, the previous table, is deferred."""

    AGENCY_CHANNEL_SCOPE = 1
    AGENCY_CHANNEL = 2
    AGENCY = 3
    GROUP_CHANNEL_SCOPE = 4
    GROUP_CHANNEL = 5
    GROUP = 6
    EXPLICIT_ZERO = 8


class ZeroReason(StrEnum):
    """Why a rate is an explicit zero rather than a negotiated one."""

    NO_SCHEDULE = "no_schedule"
    NO_SCHEDULE_FOR_YEAR = "no_schedule_for_year"


@dataclass(frozen=True)
class Bracket:
    """Revenue from `lower` (included) up to `upper` (excluded, none for the last bracket) accrues at `rate`."""

    lower: Decimal
    upper: Decimal | None
    rate: Decimal

    def __post_init__(self) -> None:
        for name in ("lower", "upper", "rate"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal, not {type(value).__name__}")


def validate_bracket_table(brackets: tuple[Bracket, ...]) -> None:
    """A table starts at 0, each bracket begins where the previous ends, and only the last is open."""
    if not brackets:
        raise RebateRuleError("bracket_table_empty", "a bracket table needs at least one bracket")
    if brackets[0].lower != 0:
        raise RebateRuleError("bracket_table_must_start_at_zero", "the first bracket must start at 0")
    for previous, bracket in zip(brackets, brackets[1:]):
        if previous.upper is None or previous.upper != bracket.lower:
            raise RebateRuleError("bracket_table_not_contiguous", "each bracket must begin where the previous one ends")
    for bracket in brackets:
        if bracket.upper is not None and bracket.upper <= bracket.lower:
            raise RebateRuleError("bracket_table_not_contiguous", "a bracket's upper threshold must exceed its lower")
    if brackets[-1].upper is not None:
        raise RebateRuleError("last_bracket_must_be_open", "the last bracket must have no upper threshold")


@dataclass(frozen=True)
class RebateSchedule:
    """A bracket table with a validity period. An agency exception names its agency; `channel` and `scope`
    of None mean any channel and any scope."""

    schedule_id: int
    group_id: int
    agency_id: int | None
    channel: str | None
    scope: str | None
    valid_from: date
    valid_to: date | None
    brackets: tuple[Bracket, ...]

    def __post_init__(self) -> None:
        validate_bracket_table(self.brackets)

    def in_force_on(self, day: date) -> bool:
        return self.valid_from <= day and (self.valid_to is None or day <= self.valid_to)


@dataclass(frozen=True)
class RebateFlight:
    """What the rebate engine needs to know about a flight. `revenue` is the flight's full revenue."""

    flight_id: int
    flight_start: date
    flight_end: date
    group_id: int
    agency_id: int
    channel: str
    scope: str
    revenue: Decimal


@dataclass(frozen=True)
class ResolvedRebate:
    schedule: RebateSchedule | None
    step: LadderStep
    agency_exception: bool
    source_year: int | None
    zero_reason: ZeroReason | None


@dataclass(frozen=True)
class BracketCharge:
    """The part of a flight's revenue that fell in one bracket, and the rebate it accrued."""

    lower: Decimal
    upper: Decimal | None
    rate: Decimal
    amount: Decimal
    rebate: Decimal


@dataclass(frozen=True)
class BracketBreakdown:
    """The exact rebate of a flight, with the charge of each bracket it touched. Nothing is rounded."""

    charges: tuple[BracketCharge, ...]
    rebate: Decimal
    effective_rate: Decimal


@dataclass(frozen=True)
class CounterKey:
    """The annual counter a flight accrues on. The agency is set only when an agency exception priced it."""

    group_id: int
    agency_id: int | None
    channel: str
    year: int


@dataclass(frozen=True)
class FlightRebate:
    """The rebate of one flight, with the data `applied_rates` will freeze. Nothing is persisted here."""

    flight_id: int
    counter: CounterKey
    step: LadderStep
    agency_exception: bool
    source_year: int | None
    zero_reason: ZeroReason | None
    schedule_id: int | None
    effective_rate: Decimal
    position_before: Decimal
    position_after: Decimal
    charges: tuple[BracketCharge, ...]
    rebate: Decimal


@dataclass(frozen=True)
class NewRebateSchedule:
    """A schedule to store, referring to its group, agency and channel by id. Its table is validated on creation."""

    holding_group_id: int
    agency_id: int | None
    channel_id: int | None
    scope: str | None
    valid_from: date
    valid_to: date | None
    brackets: tuple[Bracket, ...]

    def __post_init__(self) -> None:
        validate_bracket_table(self.brackets)
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise RebateRuleError("validity_ends_before_it_starts", "valid_to must not be before valid_from")
