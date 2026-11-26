from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.domain.exceptions import FlightNotFoundError
from app.domain.repositories.billing_adjustment_repository import AdjustableFlight, BillingAdjustmentTransaction
from app.domain.services.billing_adjustment import validate_adjustment
from app.domain.services.flight_margin import committed_billing
from app.domain.value_objects.billing import AdjustmentEntry, BillingBasis
from app.domain.value_objects.review import ReviewCause
from app.domain.value_objects.volume_commitment import VolumeCommitment


@dataclass(frozen=True)
class AdjustmentResult:
    """The adjustment written and the billing the flight has after it."""

    entry: AdjustmentEntry
    billing: Decimal


class BillingAdjustmentService:
    """Adjusts the billing of an ended, unfrozen committed flight, and reads its history, each in one transaction.

    A write takes the lock of the flight's month before it checks anything, the lock the closing and the carry-over
    take: a closing never freezes a flight while it is adjusted, and a write that waited for a closing finds its flight
    frozen.
    """

    def __init__(
        self, transaction: BillingAdjustmentTransaction, today: Callable[[], date], now: Callable[[], datetime]
    ) -> None:
        self._transaction = transaction
        self._today = today
        self._now = now

    def adjust(
        self, flight_id: int, basis: BillingBasis, amount: Decimal | None, reason: str, user_id: int
    ) -> AdjustmentResult:
        try:
            result = self._adjust(flight_id, basis, amount, reason, user_id)
        except BaseException:
            self._transaction.rollback()
            raise
        self._transaction.commit()
        return result

    def history(self, flight_id: int) -> list[AdjustmentEntry]:
        """Every adjustment of the flight, latest first; the first is the one in force."""
        if self._transaction.get_flight(flight_id) is None:
            raise FlightNotFoundError(f"flight {flight_id} does not exist")
        return self._transaction.adjustments(flight_id)

    def _locked_flight(self, flight_id: int) -> AdjustableFlight:
        flight = self._transaction.get_flight(flight_id)
        if flight is None:
            raise FlightNotFoundError(f"flight {flight_id} does not exist")
        self._transaction.lock_month(flight.window.period_year, flight.window.period_month)
        # Read again under the lock: a closing that held it may have frozen the flight meanwhile.
        refreshed = self._transaction.get_flight(flight_id)
        if refreshed is None:
            raise FlightNotFoundError(f"flight {flight_id} does not exist")
        return refreshed

    def _adjust(
        self, flight_id: int, basis: BillingBasis, amount: Decimal | None, reason: str, user_id: int
    ) -> AdjustmentResult:
        flight = self._locked_flight(flight_id)
        adjustment = validate_adjustment(
            basis=basis, amount=amount, reason=reason, is_target_line=flight.volume_commitment is VolumeCommitment.TARGET,
            flight_end=flight.window.flight_end, frozen=flight.frozen, as_of=self._today() - timedelta(days=1),
        )
        at = self._now()
        entry = self._transaction.add_adjustment(flight_id, adjustment, reason, user_id, at)
        # A reviewed campaign goes back to pending review, in this very transaction.
        self._transaction.reopen_review_if_reviewed(flight_id, ReviewCause.ADJUSTMENT, user_id, at)
        # The billing after it: the facts read now carry the adjustment just written, as the margin read will.
        facts = self._transaction.flight_facts(flight_id)
        billing = committed_billing(
            contracted=facts.contracted_impressions, carryover=facts.carryover,
            carryover_billable=facts.carryover_billable, delivered=facts.delivered, sale_cpm=facts.sale_cpm,
            adjustment=facts.adjustment,
        )
        return AdjustmentResult(entry=entry, billing=billing.amount)
