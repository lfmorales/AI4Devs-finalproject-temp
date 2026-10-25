"""The registration request: optional line dates and monthly volumes, and inverted dates refused as the schema reads them."""

from datetime import date

import pytest

from app.domain.exceptions import LineDatesInvalidError
from app.presentation.schemas.campaign import CampaignLineCreateRequest

LINE = {
    "dsp_id": 1, "channel_id": 1, "format_id": 1, "scope": "national",
    "market_description": "Spain", "contracted_impressions": 1000, "sale_cpm": "5.00",
}


def test_a_line_without_dates_or_monthly_volumes_is_accepted():
    line = CampaignLineCreateRequest(**LINE)

    assert (line.start_date, line.end_date, line.monthly_volumes) == (None, None, None)


def test_a_line_with_dates_and_monthly_volumes_keeps_them():
    line = CampaignLineCreateRequest(
        **LINE,
        start_date="2026-01-10",
        end_date="2026-02-20",
        monthly_volumes=[{"year": 2026, "month": 1, "volume": 400}, {"year": 2026, "month": 2, "volume": 600}],
    )

    assert (line.start_date, line.end_date) == (date(2026, 1, 10), date(2026, 2, 20))
    assert [(v.year, v.month, v.volume) for v in line.monthly_volumes] == [(2026, 1, 400), (2026, 2, 600)]


def test_only_one_of_the_two_dates_is_accepted():
    CampaignLineCreateRequest(**LINE, start_date="2026-01-10")
    CampaignLineCreateRequest(**LINE, end_date="2026-01-10")


def test_a_one_day_line_is_accepted():
    CampaignLineCreateRequest(**LINE, start_date="2026-01-10", end_date="2026-01-10")


def test_inverted_dates_are_refused_with_the_business_error():
    with pytest.raises(LineDatesInvalidError):
        CampaignLineCreateRequest(**LINE, start_date="2026-02-01", end_date="2026-01-31")


def test_a_month_outside_one_to_twelve_is_a_validation_error():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CampaignLineCreateRequest(**LINE, monthly_volumes=[{"year": 2026, "month": 13, "volume": 10}])


def test_the_api_answers_inverted_line_dates_with_the_global_error_body(authenticated_client):
    payload = {
        "name": "CAMP-INVERTED-DATES", "display_name": "Inverted", "agency_id": 1, "advertiser_id": 1,
        "campaign_type_id": 1, "sector_id": 1, "sales_rep_id": 1,
        "start_date": "2026-01-01", "end_date": "2026-03-31",
        "order_reference": "PO-INVERTED-DATES", "order_received_on": "2025-12-15",
        "lines": [{**LINE, "start_date": "2026-02-10", "end_date": "2026-02-01"}],
    }

    response = authenticated_client.post("/campaigns", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "line_dates_invalid"
    assert set(response.json()) == {"code", "message"}
