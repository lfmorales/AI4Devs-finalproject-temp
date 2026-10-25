from datetime import date

from pydantic import BaseModel, Field

from app.presentation.schemas.campaign import LineDatesRequest


class FlightPreviewRequest(LineDatesRequest):
    """A line to preview: the campaign's dates, the line's own optional dates and its total volume."""

    campaign_start_date: date
    campaign_end_date: date
    contracted_impressions: int = Field(..., gt=0)


class FlightPreviewFlight(BaseModel):
    period_year: int
    period_month: int
    flight_start: date
    flight_end: date
    contracted_impressions: int


class FlightPreviewResponse(BaseModel):
    """The line's effective dates and the flights its volume would be split into."""

    start_date: date
    end_date: date
    flights: list[FlightPreviewFlight]
