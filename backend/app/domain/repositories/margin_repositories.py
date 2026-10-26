from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from app.domain.value_objects.priced_flight import FlightFacts, PlatformRates, PricedFlight
from app.domain.value_objects.rebate import CounterKey, RebateSchedule


class RebateScheduleRepository(ABC):
    @abstractmethod
    def list_schedules(self) -> list[RebateSchedule]:
        """Every schedule with its brackets, the channel by name."""


class PlatformRateRepository(ABC):
    @abstractmethod
    def current_rates(self) -> PlatformRates:
        """The platform rates in force: for each level and key, the latest setting; the system value included."""


class MarginFlightRepository(ABC):
    @abstractmethod
    def open_ended_flights(self, year: int, month: int, as_of: date) -> list[FlightFacts]:
        """Flights of that calendar month that ended on or before `as_of` and have no frozen rates.

        Ordered by `flight_start` and then by flight id. Delivery and media cost are summed over each flight's
        window in the database.
        """

    @abstractmethod
    def earliest_month_with_open_flights(self, year: int, before_month: int, as_of: date) -> int | None:
        """The earliest month of `year` before `before_month` that has an ended flight without frozen rates."""


class AppliedRateRepository(ABC):
    @abstractmethod
    def opening_positions(self, year: int) -> dict[CounterKey, Decimal]:
        """Where each counter of `year` stands: the position after its latest frozen flight."""

    @abstractmethod
    def count_frozen(self, year: int, month: int) -> int:
        """How many flights of that calendar month already have frozen rates."""

    @abstractmethod
    def save(self, priced: Sequence[PricedFlight], closed_at: datetime, closed_by: int) -> None:
        """Freeze the rates of these flights, one row each with its bracket breakdown. Rows are only added."""


class MarginClosingTransaction(ABC):
    """The transactional boundary of closing a month: its writes land whole or not at all."""

    schedules: RebateScheduleRepository
    platform_rates: PlatformRateRepository
    flights: MarginFlightRepository
    applied_rates: AppliedRateRepository

    @abstractmethod
    def lock_month(self, year: int, month: int) -> None:
        """Serialise closings of one month: held until the transaction ends."""

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...
