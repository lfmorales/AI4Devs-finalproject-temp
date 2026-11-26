from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.domain.exceptions import FlightNotFoundError
from app.domain.repositories.carryover_repository import CarryoverFlight, CarryoverTransaction
from app.domain.services.carryover import delivery_target, previous_flight_of, validate_billable, validate_carryover
from app.domain.value_objects.volume_commitment import VolumeCommitment


@dataclass(frozen=True)
class CarryoverResult:
    """The carry-over of a flight after a write. Volumes only: nothing here is an amount or a billable flag."""

    flight_id: int
    delivery_metric: str
    contracted_impressions: int
    carryover: int
    delivery_target: int
    reason: str
    set_by: int
    set_at: datetime


@dataclass(frozen=True)
class BillableResult:
    flight_id: int
    carryover: int
    billable: bool
    set_by: int
    set_at: datetime


class CarryoverService:
    """Writes the carry-over of a flight and decides whether it is billable, each in one transaction.

    Both take the lock of the flight's month before they check anything, so a closing never freezes a flight while a
    carry-over is being written, and a write that waited for a closing finds its month closed.
    """

    def __init__(
        self, transaction: CarryoverTransaction, today: Callable[[], date], now: Callable[[], datetime]
    ) -> None:
        self._transaction = transaction
        self._today = today
        self._now = now

    def put_carryover(self, flight_id: int, volume: int, reason: str, user_id: int) -> CarryoverResult:
        try:
            result = self._put_carryover(flight_id, volume, reason, user_id)
        except BaseException:
            self._transaction.rollback()
            raise
        self._transaction.commit()
        return result

    def set_billable(self, flight_id: int, billable: bool, user_id: int) -> BillableResult:
        try:
            result = self._set_billable(flight_id, billable, user_id)
        except BaseException:
            self._transaction.rollback()
            raise
        self._transaction.commit()
        return result

    def _locked_flight(self, flight_id: int) -> CarryoverFlight:
        flight = self._transaction.get_flight(flight_id)
        if flight is None:
            raise FlightNotFoundError(f"flight {flight_id} does not exist")
        self._transaction.lock_month(flight.window.period_year, flight.window.period_month)
        # Read again under the lock: a closing that held it may have closed the month meanwhile.
        refreshed = self._transaction.get_flight(flight_id)
        if refreshed is None:
            raise FlightNotFoundError(f"flight {flight_id} does not exist")
        return refreshed

    def _put_carryover(self, flight_id: int, volume: int, reason: str, user_id: int) -> CarryoverResult:
        flight = self._locked_flight(flight_id)
        line = self._transaction.line_flights(flight.line_id)
        previous_window = previous_flight_of([item.window for item in line], flight.window)
        previous = None
        if previous_window is not None:
            previous_id = next(item.flight_id for item in line if item.window == previous_window)
            previous = self._transaction.previous_flight_figures(previous_id)
        # D-1, the last day counted: a flight ending on it has ended.
        validate_carryover(
            volume=volume, reason=reason, previous=previous, receiving_month_closed=flight.month_closed,
            as_of=self._today() - timedelta(days=1),
        )
        at = self._now()
        self._transaction.write_carryover(flight_id, volume, reason, user_id, at)
        return CarryoverResult(
            flight_id=flight_id, delivery_metric=flight.delivery_metric, contracted_impressions=flight.contracted,
            carryover=volume, delivery_target=delivery_target(flight.contracted, volume), reason=reason,
            set_by=user_id, set_at=at,
        )

    def _set_billable(self, flight_id: int, billable: bool, user_id: int) -> BillableResult:
        flight = self._locked_flight(flight_id)
        validate_billable(
            is_target_line=flight.volume_commitment is VolumeCommitment.TARGET, billable=billable, carryover=flight.carryover,
            month_closed=flight.month_closed,
        )
        at = self._now()
        self._transaction.write_billable(flight_id, billable, user_id, at)
        return BillableResult(flight_id=flight_id, carryover=flight.carryover, billable=billable, set_by=user_id, set_at=at)
