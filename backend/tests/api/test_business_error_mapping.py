"""Business-rule errors of the campaign line model leave through the global handlers as {"code","message"}."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.exceptions import (
    DomainError,
    FlightVolumeNotPositiveError,
    FlightVolumesIncompleteError,
    FlightVolumesMismatchError,
    LineDatesInvalidError,
    LineDatesOutsideCampaignError,
    VolumeTooSmallForFlightsError,
)
from app.presentation.errors import register_exception_handlers

CASES = [
    (LineDatesOutsideCampaignError, "line_dates_outside_campaign"),
    (LineDatesInvalidError, "line_dates_invalid"),
    (VolumeTooSmallForFlightsError, "volume_too_small_for_flights"),
    (FlightVolumesIncompleteError, "flight_volumes_incomplete"),
    (FlightVolumesMismatchError, "flight_volumes_mismatch"),
    (FlightVolumeNotPositiveError, "flight_volume_not_positive"),
]


@pytest.mark.parametrize(("error_type", "code"), CASES)
def test_a_line_model_error_is_an_unprocessable_request_with_a_fixed_body(error_type: type[DomainError], code: str):
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise error_type("internal detail: line 3 starts 2026-01-01")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}
    assert response.json()["code"] == code
    assert "internal detail" not in response.text
