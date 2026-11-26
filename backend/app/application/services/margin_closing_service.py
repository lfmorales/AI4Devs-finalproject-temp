from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.domain.exceptions import MonthDeliveryNotLoadedError, MonthNotReviewedError, PreviousMonthOpenError
from app.domain.repositories.margin_repositories import MarginClosingTransaction
from app.domain.services.monthly_review import review_state
from app.domain.services.priced_flights import price_flights
from app.domain.value_objects.review import ReviewState

# A campaign in one of these states blocks the closing of its month; a reviewed or closed one does not.
_BLOCKING_STATES = frozenset({ReviewState.IN_PROGRESS, ReviewState.PENDING_REVIEW})


@dataclass(frozen=True)
class ClosingResult:
    """`closed` flights were frozen by this request, `already_closed` before it; the month holds `closings` headers."""

    year: int
    month: int
    closed: int
    already_closed: int
    closings: int


class MarginClosingService:
    """Freezes the flights that ended in a month, once, in order, and all or nothing.

    It prices the flights with the same domain function the reads use, and only writes what it returns: their rates,
    their snapshots and one header for the run, in one transaction. A run that freezes nothing writes nothing.

    Under the month's lock it checks, in order, that no earlier month of the year is open, that no campaign of the month
    is in progress, that every DSP of the month's ended and unfrozen flights has loaded the month's last day, and that
    every campaign of the month is reviewed or closed; the first that fails refuses the closing.
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
        blocking = tuple(
            (campaign.campaign_name, state)
            for campaign in self._transaction.flights.campaigns_of_the_month(year, month, as_of)
            if (state := review_state(campaign.counts, campaign.latest_event)) in _BLOCKING_STATES
        )
        # A flight still running comes first: while it runs, no DSP can have loaded the month's last day.
        if any(state is ReviewState.IN_PROGRESS for _, state in blocking):
            raise MonthNotReviewedError(year, month, blocking)
        # A target flight earns what its DSP reports and a committed one bills its delivery: its month waits until the
        # DSP has loaded the month's last day.
        not_loaded = self._transaction.flights.dsps_without_the_months_last_day(year, month, as_of)
        if not_loaded:
            raise MonthDeliveryNotLoadedError(year, month, not_loaded[0])
        if blocking:
            raise MonthNotReviewedError(year, month, blocking)

        already_closed = self._transaction.applied_rates.count_frozen(year, month)
        flights = self._transaction.flights.open_ended_flights(year, month, as_of)
        if not flights:
            return self._result(year, month, closed=0, already_closed=already_closed)

        priced = price_flights(
            self._transaction.schedules.list_schedules(),
            self._transaction.platform_rates.current_rates(),
            flights,
            as_of,
            self._transaction.applied_rates.opening_positions(year),
        )
        if priced:
            closed_at = self._now()
            closing_id = self._transaction.closings.add_closing(
                year, month, closed_at, closed_by, as_of, [item.facts.flight_id for item in priced]
            )
            self._transaction.applied_rates.save(priced, closed_at, closed_by, closing_id)
        return self._result(year, month, closed=len(priced), already_closed=already_closed)

    def _result(self, year: int, month: int, closed: int, already_closed: int) -> ClosingResult:
        closings = self._transaction.closings.count_closings(year, month)
        return ClosingResult(year, month, closed=closed, already_closed=already_closed, closings=closings)
