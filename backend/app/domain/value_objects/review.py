"""The monthly review of a campaign: its states, the kinds of event stored and the causes of a reopening."""

from enum import StrEnum


class ReviewState(StrEnum):
    """Where a campaign stands in a month. Derived, never stored: only the review events are."""

    IN_PROGRESS = "in_progress"
    PENDING_REVIEW = "pending_review"
    REVIEWED = "reviewed"
    CLOSED = "closed"


class ReviewKind(StrEnum):
    """The two kinds of event stored: a review, and a reopening that returns the campaign to pending review."""

    REVIEWED = "reviewed"
    REOPENED = "reopened"


class ReviewCause(StrEnum):
    """Why a review was reopened: the user withdrew it, or an edit changed the billing after it."""

    WITHDRAWN = "withdrawn"
    ADJUSTMENT = "adjustment"
    CARRYOVER = "carryover"
    CARRYOVER_BILLABLE = "carryover_billable"

    @property
    def is_an_edit(self) -> bool:
        """The three edits name the flight they changed; a withdrawal names none."""
        return self is not ReviewCause.WITHDRAWN
