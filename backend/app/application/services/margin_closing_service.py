from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.domain.exceptions import PreviousMonthOpenError
from app.domain.repositories.margin_repositories import MarginClosingTransaction
from app.domain.services.priced_flights import price_flights


@dataclass(frozen=True)
class ClosingResult:
    year: int
    month: int
    closed: int
    already_closed: int


class MarginClosingService:
    """Freezes the rates of the flights that ended in a month, once, in order, and all or nothing.

    It prices the flights with the same domain function the reads use, and only writes what it returns.
    """

    def __init__(
        self, transaction: MarginClosingTransaction, today: Callable[[], date], now: Callable[[], datetime]
    ) -> None:
        self._transaction = transaction
        self._today = today
        self._now = now

    def close_month(self, year: int, month: int, closed_by: int) -> ClosingResult:
        try:
            result = self._close(year, month, closed_by)
        except BaseException:
            self._transaction.rollback()
            raise
        self._transaction.commit()
        return result

    def _close(self, year: int, month: int, closed_by: int) -> ClosingResult:
        as_of = self._today() - timedelta(days=1)
        self._transaction.lock_month(year, month)
        blocking_month = self._transaction.flights.earliest_month_with_open_flights(year, month, as_of)
        if blocking_month is not None:
            raise PreviousMonthOpenError(year, blocking_month)

        already_closed = self._transaction.applied_rates.count_frozen(year, month)
        flights = self._transaction.flights.open_ended_flights(year, month, as_of)
        if not flights:
            return ClosingResult(year, month, closed=0, already_closed=already_closed)

        priced = price_flights(
            self._transaction.schedules.list_schedules(),
            self._transaction.platform_rates.current_rates(),
            flights,
            as_of,
            self._transaction.applied_rates.opening_positions(year),
        )
        self._transaction.applied_rates.save(priced, self._now(), closed_by)
        return ClosingResult(year, month, closed=len(priced), already_closed=already_closed)
