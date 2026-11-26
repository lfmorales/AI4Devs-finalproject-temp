from datetime import datetime

from pydantic import BaseModel, Field

from app.application.services.monthly_review_service import ReviewResult
from app.domain.value_objects.review import ReviewState


class ReviewRequest(BaseModel):
    campaign_id: int = Field(ge=1)
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class ReviewResponse(BaseModel):
    """A campaign in a month after a review or a withdrawal."""

    campaign_id: int
    year: int
    month: int
    state: ReviewState = Field(description="`reviewed` after a review, `pending_review` after a withdrawal.")
    set_by: int = Field(description="The user who wrote the event that put the campaign in this state.")
    set_at: datetime = Field(description="When that event was written.")

    @classmethod
    def from_result(cls, result: ReviewResult) -> "ReviewResponse":
        return cls(
            campaign_id=result.campaign_id, year=result.year, month=result.month, state=result.state,
            set_by=result.set_by, set_at=result.set_at,
        )
