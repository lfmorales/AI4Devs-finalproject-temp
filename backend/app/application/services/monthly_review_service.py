from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.domain.exceptions import CampaignNotFoundError, MonthDeliveryNotLoadedError, MonthlyReviewError
from app.domain.repositories.monthly_review_repository import MonthlyReviewTransaction, ReviewEvent
from app.domain.services.monthly_review import review_state
from app.domain.value_objects.review import ReviewCause, ReviewKind, ReviewState


@dataclass(frozen=True)
class ReviewResult:
    """A campaign in a month after a review or a withdrawal: its state and the latest event that put it there."""

    campaign_id: int
    year: int
    month: int
    state: ReviewState
    set_by: int
    set_at: datetime
    created: bool


class MonthlyReviewService:
    """Marks a campaign reviewed in a month, withdraws the review, and reads the state, each in one transaction.

    The state is derived, as of D-1, from the campaign's flights of the month and from its latest review event; only the
    events are stored. A write takes the lock of the month before it checks anything, the lock the closing and the other
    edits of the month take.
    """

    def __init__(
        self, transaction: MonthlyReviewTransaction, today: Callable[[], date], now: Callable[[], datetime]
    ) -> None:
        self._transaction = transaction
        self._today = today
        self._now = now

    def review(self, campaign_id: int, year: int, month: int, user_id: int) -> ReviewResult:
        """Mark the campaign reviewed. A campaign already reviewed answers its current review and writes nothing."""
        return self._write(campaign_id, year, month, user_id, withdraw=False)

    def withdraw(self, campaign_id: int, year: int, month: int, user_id: int) -> ReviewResult:
        """Withdraw the review: a reopening event, so the campaign goes back to pending review."""
        return self._write(campaign_id, year, month, user_id, withdraw=True)

    def state(self, campaign_id: int, year: int, month: int) -> ReviewState:
        """The state of the campaign in the month, as of D-1."""
        period_id, _ = self._period(campaign_id, year, month)
        return self._state_of(period_id, self._transaction.latest_event(period_id))

    def _write(self, campaign_id: int, year: int, month: int, user_id: int, withdraw: bool) -> ReviewResult:
        try:
            result = self._write_in_transaction(campaign_id, year, month, user_id, withdraw)
        except BaseException:
            self._transaction.rollback()
            raise
        self._transaction.commit()
        return result

    def _period(self, campaign_id: int, year: int, month: int) -> tuple[int, int]:
        if not self._transaction.campaign_exists(campaign_id):
            raise CampaignNotFoundError(f"campaign {campaign_id} does not exist")
        period_id = self._transaction.period_of(campaign_id, year, month)
        if period_id is None:
            raise MonthlyReviewError("campaign_month_not_found", "the campaign has no flights in that month")
        return period_id, year * 100 + month

    def _state_of(self, period_id: int, latest: ReviewEvent | None) -> ReviewState:
        counts = self._transaction.flight_counts(period_id, self._today() - timedelta(days=1))
        if counts.total == 0:
            raise MonthlyReviewError("campaign_month_not_found", "the campaign has no flights in that month")
        return review_state(counts, None if latest is None else latest.kind)

    def _write_in_transaction(
        self, campaign_id: int, year: int, month: int, user_id: int, withdraw: bool
    ) -> ReviewResult:
        if not self._transaction.campaign_exists(campaign_id):
            raise CampaignNotFoundError(f"campaign {campaign_id} does not exist")
        self._transaction.lock_month(year, month)
        period_id, _ = self._period(campaign_id, year, month)
        latest = self._transaction.latest_event(period_id)
        state = self._state_of(period_id, latest)
        if state is ReviewState.CLOSED:
            raise MonthlyReviewError("campaign_month_closed", "the month of the campaign is closed")
        if withdraw:
            if state is not ReviewState.REVIEWED:
                raise MonthlyReviewError("not_reviewed", "the campaign is not reviewed in that month")
            kind, cause = ReviewKind.REOPENED, ReviewCause.WITHDRAWN
        else:
            if state is ReviewState.IN_PROGRESS:
                raise MonthlyReviewError("campaign_month_in_progress", "a flight of the campaign has not ended yet")
            if state is ReviewState.REVIEWED:
                assert latest is not None
                return ReviewResult(campaign_id, year, month, state, latest.created_by, latest.created_at, created=False)
            # A reviewed campaign never rests on an incomplete delivery: that is why an ingestion does not reopen it.
            not_loaded = self._transaction.dsps_without_the_months_last_day(period_id, year, month)
            if not_loaded:
                raise MonthDeliveryNotLoadedError(year, month, not_loaded[0], next_step="review the campaign")
            kind, cause = ReviewKind.REVIEWED, None
        event = self._transaction.add_event(period_id, kind, cause, None, user_id, self._now())
        new_state = ReviewState.PENDING_REVIEW if withdraw else ReviewState.REVIEWED
        return ReviewResult(campaign_id, year, month, new_state, event.created_by, event.created_at, created=True)
