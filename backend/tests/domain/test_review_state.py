"""The review state of a campaign in a month (finance/monthly-review, «A campaign has a review state in each month»).

Only the review events are stored. The four states are derived, as of D-1, from the campaign's flights of the month
(how many there are, how many have ended, how many a closing froze) and from the latest review event.
"""

import pytest

from app.domain.services.monthly_review import FlightCounts, review_state
from app.domain.value_objects.review import ReviewCause, ReviewKind, ReviewState


def _state(total: int, ended: int, frozen: int, latest: ReviewKind | None = None) -> ReviewState:
    return review_state(FlightCounts(total=total, ended=ended, frozen=frozen), latest)


def test_a_campaign_with_a_flight_still_running_is_in_progress() -> None:
    # Two October flights, one ended and one still running.
    assert _state(total=2, ended=1, frozen=0) is ReviewState.IN_PROGRESS


def test_a_campaign_whose_flights_have_all_ended_and_has_no_review_is_pending_review() -> None:
    assert _state(total=2, ended=2, frozen=0) is ReviewState.PENDING_REVIEW


def test_a_campaign_whose_latest_event_is_a_review_is_reviewed() -> None:
    assert _state(total=2, ended=2, frozen=0, latest=ReviewKind.REVIEWED) is ReviewState.REVIEWED


def test_a_campaign_whose_latest_event_is_a_reopening_is_pending_review() -> None:
    assert _state(total=2, ended=2, frozen=0, latest=ReviewKind.REOPENED) is ReviewState.PENDING_REVIEW


def test_a_campaign_whose_flights_are_all_frozen_is_closed() -> None:
    assert _state(total=2, ended=2, frozen=2, latest=ReviewKind.REVIEWED) is ReviewState.CLOSED


def test_a_closed_campaign_is_closed_whatever_its_reviews_say() -> None:
    assert _state(total=1, ended=1, frozen=1) is ReviewState.CLOSED
    assert _state(total=1, ended=1, frozen=1, latest=ReviewKind.REOPENED) is ReviewState.CLOSED


def test_a_flight_that_is_not_frozen_keeps_the_campaign_from_being_closed() -> None:
    # A flight registered in a month already closed: the campaign goes back to its review.
    assert _state(total=2, ended=2, frozen=1, latest=ReviewKind.REVIEWED) is ReviewState.REVIEWED
    assert _state(total=2, ended=2, frozen=1) is ReviewState.PENDING_REVIEW


def test_a_running_flight_wins_over_a_review() -> None:
    # Reviewed once, then a flight registered in the month that has not ended.
    assert _state(total=2, ended=1, frozen=0, latest=ReviewKind.REVIEWED) is ReviewState.IN_PROGRESS


def test_a_campaign_with_no_flights_in_the_month_has_no_state() -> None:
    with pytest.raises(ValueError):
        _state(total=0, ended=0, frozen=0)


@pytest.mark.parametrize(
    ("total", "ended", "frozen"), [(-1, 0, 0), (1, 2, 0), (1, 0, 1), (2, 1, 2)], ids=["negative", "more-ended", "frozen-not-ended", "more-frozen"]
)
def test_counts_that_cannot_exist_are_refused(total: int, ended: int, frozen: int) -> None:
    with pytest.raises(ValueError):
        FlightCounts(total=total, ended=ended, frozen=frozen)


def test_the_states_have_the_names_the_api_gives_them() -> None:
    assert [state.value for state in ReviewState] == ["in_progress", "pending_review", "reviewed", "closed"]


def test_the_causes_of_a_reopening_name_the_withdrawal_and_the_three_edits() -> None:
    assert {cause.value for cause in ReviewCause} == {"withdrawn", "adjustment", "carryover", "carryover_billable"}
    assert {cause for cause in ReviewCause if cause.is_an_edit} == {
        ReviewCause.ADJUSTMENT, ReviewCause.CARRYOVER, ReviewCause.CARRYOVER_BILLABLE,
    }
