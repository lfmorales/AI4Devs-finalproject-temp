from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.domain.services.monthly_review import FlightCounts
from app.domain.value_objects.platform_rate import NewPlatformRateSetting, PlatformRateSetting
from app.domain.value_objects.priced_flight import FlightFacts, PlatformRates, PricedFlight, ReadFlight
from app.domain.value_objects.rebate import CounterKey, NewRebateSchedule, RebateSchedule
from app.domain.value_objects.review import ReviewKind


@dataclass(frozen=True)
class CampaignMonthStanding:
    """A campaign with flights in a month, as the closing needs it to derive its review state: its name, its flights'
    counts as of D-1 and the kind of its latest review event in the month, if any."""

    campaign_id: int
    campaign_name: str
    counts: FlightCounts
    latest_event: ReviewKind | None


class RebateScheduleRepository(ABC):
    @abstractmethod
    def list_schedules(self) -> list[RebateSchedule]:
        """Every schedule with its brackets, the channel by name."""

    @abstractmethod
    def add_schedule(self, new: NewRebateSchedule) -> int:
        """Store a schedule and its brackets and return its id.

        Raises `schedule_overlaps_existing` when another schedule of the same key is in force during part of its
        validity, and `reference_not_found` when its group, agency or channel does not exist.
        """


class PlatformRateRepository(ABC):
    @abstractmethod
    def current_rates(self) -> PlatformRates:
        """The platform rates in force: for each level and key, the latest setting; the system value included."""

    @abstractmethod
    def add_setting(self, new: NewPlatformRateSetting) -> PlatformRateSetting:
        """Store a setting, stamped with its author and the time. Raises `reference_not_found` for a missing key."""


class MarginFlightRepository(ABC):
    @abstractmethod
    def open_ended_flights(self, year: int, month: int, as_of: date) -> list[FlightFacts]:
        """Flights of that calendar month that ended on or before `as_of` and have no frozen rates.

        Ordered by `flight_start` and then by flight id. Delivery and media cost are summed over each flight's
        window in the database.
        """

    @abstractmethod
    def dsps_without_the_months_last_day(self, year: int, month: int, as_of: date) -> list[str]:
        """The DSPs, by name, of the month's ended and unfrozen flights, committed or target, that have no succeeded ingestion batch
        whose window includes the month's last day. Empty when the month can be closed."""

    @abstractmethod
    def campaigns_of_the_month(self, year: int, month: int, as_of: date) -> list[CampaignMonthStanding]:
        """Every campaign with flights in the month, by name and then id, with what derives its review state."""

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
    def save(
        self, priced: Sequence[PricedFlight], closed_at: datetime, closed_by: int, month_closing_id: int
    ) -> None:
        """Freeze these flights: one row each with its rates and bracket breakdown, and its snapshot under the closing
        header `month_closing_id`. Rows are only added."""


class MonthClosingRepository(ABC):
    @abstractmethod
    def add_closing(
        self, year: int, month: int, closed_at: datetime, closed_by: int, as_of: date, flight_ids: Sequence[int]
    ) -> int:
        """Record one closing run of the month and return its header's id.

        The header names, for each DSP of the lines of `flight_ids`, the latest succeeded ingestion batch of that DSP
        (latest `finished_at`, then highest id); a DSP without one is not named.
        """

    @abstractmethod
    def count_closings(self, year: int, month: int) -> int:
        """How many closing headers the month holds: closed when one or more."""


class MarginClosingTransaction(ABC):
    """The transactional boundary of closing a month: its writes land whole or not at all."""

    schedules: RebateScheduleRepository
    platform_rates: PlatformRateRepository
    flights: MarginFlightRepository
    applied_rates: AppliedRateRepository
    closings: MonthClosingRepository

    @abstractmethod
    def lock_month(self, year: int, month: int) -> None:
        """Serialise closings of one month: held until the transaction ends."""

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...


class MarginReadRepository(ABC):
    @abstractmethod
    def list_flights(
        self,
        as_of: date,
        year: int | None = None,
        month: int | None = None,
        campaign_id: int | None = None,
        unfrozen_only: bool = False,
    ) -> list[ReadFlight]:
        """Flights that have started by `as_of`, with delivery summed over each window in the database.

        Ordered by `flight_start` and then flight id. A frozen flight carries the rates frozen for it.
        """

    @abstractmethod
    def campaign_exists(self, campaign_id: int) -> bool: ...


class MarginMastersTransaction(ABC):
    """The transactional boundary of creating a schedule or a platform rate."""

    schedules: RebateScheduleRepository
    platform_rates: PlatformRateRepository

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...
