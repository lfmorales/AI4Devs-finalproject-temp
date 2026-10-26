from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import IntEnum, StrEnum


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
