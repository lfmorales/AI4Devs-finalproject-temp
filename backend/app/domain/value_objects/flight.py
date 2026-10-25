from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class FlightWindow:
    """The days a campaign line shares with one calendar month, both ends included."""

    period_year: int
    period_month: int
    flight_start: date
    flight_end: date

    def __post_init__(self) -> None:
        if self.flight_start > self.flight_end:
            raise ValueError("flight_start must be <= flight_end")

    @property
    def days(self) -> int:
        return (self.flight_end - self.flight_start).days + 1


@dataclass(frozen=True)
class MonthlyVolume:
    """A volume the purchase order states for one calendar month of a line."""

    period_year: int
    period_month: int
    volume: int
