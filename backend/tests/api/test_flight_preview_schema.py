"""POST /flights/preview schemas: campaign dates, optional line dates and a positive total in; dates and flights out."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.exceptions import LineDatesInvalidError
from app.presentation.schemas.flight_preview import FlightPreviewRequest, FlightPreviewResponse

BASE = {"campaign_start_date": "2026-08-01", "campaign_end_date": "2026-10-31", "contracted_impressions": 100}


def test_line_dates_are_optional():
    request = FlightPreviewRequest(**BASE)

    assert (request.start_date, request.end_date) == (None, None)
    assert request.campaign_start_date == date(2026, 8, 1) and request.campaign_end_date == date(2026, 10, 31)


def test_line_dates_are_kept_when_given():
    request = FlightPreviewRequest(**BASE, start_date="2026-09-10", end_date="2026-10-05")

    assert (request.start_date, request.end_date) == (date(2026, 9, 10), date(2026, 10, 5))


@pytest.mark.parametrize("volume", [0, -1])
def test_a_total_that_is_not_positive_is_a_validation_error(volume: int):
    with pytest.raises(ValidationError):
        FlightPreviewRequest(**{**BASE, "contracted_impressions": volume})


@pytest.mark.parametrize("missing", ["campaign_start_date", "campaign_end_date", "contracted_impressions"])
def test_campaign_dates_and_the_total_are_required(missing: str):
    with pytest.raises(ValidationError):
        FlightPreviewRequest(**{key: value for key, value in BASE.items() if key != missing})


def test_inverted_line_dates_are_refused_with_the_business_error():
    with pytest.raises(LineDatesInvalidError):
        FlightPreviewRequest(**BASE, start_date="2026-09-10", end_date="2026-09-09")


def test_the_response_lists_the_effective_dates_and_the_flights():
    response = FlightPreviewResponse(
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        flights=[{
            "period_year": 2026, "period_month": 8, "flight_start": date(2026, 8, 1),
            "flight_end": date(2026, 8, 31), "contracted_impressions": 100,
        }],
    )

    assert set(response.model_dump()) == {"start_date", "end_date", "flights"}
    assert set(response.model_dump()["flights"][0]) == {
        "period_year", "period_month", "flight_start", "flight_end", "contracted_impressions",
    }
