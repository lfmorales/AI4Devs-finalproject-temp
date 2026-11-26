"""The review state of a campaign in a month (finance/monthly-review)."""

from dataclasses import dataclass

from app.domain.value_objects.review import ReviewKind, ReviewState


@dataclass(frozen=True)
class FlightCounts:
    """The flights a campaign has in a month, as of D-1: how many there are, how many have ended and how many a closing
    froze (a frozen flight has ended)."""

    total: int
    ended: int
    frozen: int

    def __post_init__(self) -> None:
        if not 0 <= self.frozen <= self.ended <= self.total:
            raise ValueError("the frozen flights are among the ended ones, which are among all of them")


def review_state(counts: FlightCounts, latest_event: ReviewKind | None) -> ReviewState:
    """The state of a campaign in a month: closed when every flight is frozen, otherwise in progress while one has not
    ended, otherwise reviewed when its latest event is a review, otherwise pending review."""
    if counts.total == 0:
        raise ValueError("a campaign with no flights in a month has no state in it")
    if counts.frozen == counts.total:
        return ReviewState.CLOSED
    if counts.ended < counts.total:
        return ReviewState.IN_PROGRESS
    if latest_event is ReviewKind.REVIEWED:
        return ReviewState.REVIEWED
    return ReviewState.PENDING_REVIEW
