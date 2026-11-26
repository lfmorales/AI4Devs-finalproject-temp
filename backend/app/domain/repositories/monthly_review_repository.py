from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime

from app.domain.services.monthly_review import FlightCounts
from app.domain.value_objects.review import ReviewCause, ReviewKind


@dataclass(frozen=True)
class ReviewEvent:
    """One stored event of a campaign in a month: who wrote it and when."""

    kind: ReviewKind
    cause: ReviewCause | None
    created_by: int
    created_at: datetime


class MonthlyReviewTransaction(ABC):
    """The transactional boundary of reviewing or withdrawing: it lands whole or not at all."""

    @abstractmethod
    def campaign_exists(self, campaign_id: int) -> bool: ...

    @abstractmethod
    def period_of(self, campaign_id: int, year: int, month: int) -> int | None:
        """The campaign period (the campaign in that month), or None when the campaign has none."""

    @abstractmethod
    def lock_month(self, year: int, month: int) -> None:
        """Serialise this write with the closing of the month and with the other edits of it, until the end."""

    @abstractmethod
    def flight_counts(self, period_id: int, as_of: date) -> FlightCounts:
        """The flights the campaign period holds: all, the ones ended by `as_of` and the ones a closing froze."""

    @abstractmethod
    def dsps_without_the_months_last_day(self, period_id: int, year: int, month: int) -> list[str]:
        """The DSPs, by name, of the lines of the campaign period's flights that have no succeeded ingestion batch whose
        window includes the month's last day. Empty when the campaign can be reviewed."""

    @abstractmethod
    def latest_event(self, period_id: int) -> ReviewEvent | None: ...

    @abstractmethod
    def add_event(
        self, period_id: int, kind: ReviewKind, cause: ReviewCause | None, flight_id: int | None, user_id: int,
        at: datetime,
    ) -> ReviewEvent: ...

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...
