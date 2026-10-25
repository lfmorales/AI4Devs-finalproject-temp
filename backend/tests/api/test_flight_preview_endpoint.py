"""POST /flights/preview computes the flights of a line and stores nothing."""

BODY = {"campaign_start_date": "2026-08-01", "campaign_end_date": "2026-10-31", "contracted_impressions": 100}


def test_a_line_inheriting_the_campaign_dates_is_previewed_by_days(authenticated_client):
    response = authenticated_client.post("/flights/preview", json=BODY)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "start_date": "2026-08-01",
        "end_date": "2026-10-31",
        "flights": [
            {"period_year": 2026, "period_month": 8, "flight_start": "2026-08-01", "flight_end": "2026-08-31",
             "contracted_impressions": 34},
            {"period_year": 2026, "period_month": 9, "flight_start": "2026-09-01", "flight_end": "2026-09-30",
             "contracted_impressions": 32},
            {"period_year": 2026, "period_month": 10, "flight_start": "2026-10-01", "flight_end": "2026-10-31",
             "contracted_impressions": 34},
        ],
    }


def test_the_route_is_a_plain_def_that_takes_no_database_session():
    import inspect

    from app.presentation.routers import flight_preview

    endpoint = flight_preview.preview_flights
    assert not inspect.iscoroutinefunction(endpoint)
    assert "session" not in inspect.signature(endpoint).parameters


import pytest
from sqlalchemy import func, select

from app.infrastructure.persistence.models import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
    PurchaseOrderRecord,
)


def _flights(response):
    return [(f["period_month"], f["flight_start"], f["flight_end"], f["contracted_impressions"])
            for f in response.json()["flights"]]


def test_a_line_with_its_own_dates_only_gets_the_months_it_touches(authenticated_client):
    response = authenticated_client.post(
        "/flights/preview", json={**BODY, "start_date": "2026-09-10", "end_date": "2026-10-05", "contracted_impressions": 1000}
    )

    assert response.status_code == 200, response.text
    assert (response.json()["start_date"], response.json()["end_date"]) == ("2026-09-10", "2026-10-05")
    assert _flights(response) == [(9, "2026-09-10", "2026-09-30", 808), (10, "2026-10-01", "2026-10-05", 192)]


def test_a_line_inside_one_month_has_one_flight_with_the_total(authenticated_client):
    response = authenticated_client.post(
        "/flights/preview", json={**BODY, "start_date": "2026-09-03", "end_date": "2026-09-20", "contracted_impressions": 777}
    )

    assert _flights(response) == [(9, "2026-09-03", "2026-09-20", 777)]


def test_a_line_of_one_day_has_one_flight_of_one_day(authenticated_client):
    response = authenticated_client.post(
        "/flights/preview", json={**BODY, "start_date": "2026-09-30", "end_date": "2026-09-30", "contracted_impressions": 5}
    )

    assert _flights(response) == [(9, "2026-09-30", "2026-09-30", 5)]


def test_a_total_too_small_for_its_flights_is_rejected(authenticated_client):
    response = authenticated_client.post("/flights/preview", json={**BODY, "contracted_impressions": 2})

    assert response.status_code == 422
    assert response.json()["code"] == "volume_too_small_for_flights" and set(response.json()) == {"code", "message"}


@pytest.mark.parametrize("dates", [
    {"start_date": "2026-07-31"},
    {"end_date": "2026-11-01"},
    {"start_date": "2026-07-01", "end_date": "2026-12-31"},
])
def test_line_dates_outside_the_campaign_are_rejected(authenticated_client, dates):
    response = authenticated_client.post("/flights/preview", json={**BODY, **dates})

    assert response.status_code == 422
    assert response.json()["code"] == "line_dates_outside_campaign" and set(response.json()) == {"code", "message"}


def test_inverted_line_dates_are_rejected(authenticated_client):
    response = authenticated_client.post(
        "/flights/preview", json={**BODY, "start_date": "2026-09-10", "end_date": "2026-09-09"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "line_dates_invalid" and set(response.json()) == {"code", "message"}


def test_campaign_dates_in_reverse_order_leave_no_valid_line(authenticated_client):
    response = authenticated_client.post(
        "/flights/preview", json={**BODY, "campaign_start_date": "2026-10-31", "campaign_end_date": "2026-08-01"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "line_dates_invalid"


@pytest.mark.parametrize("volume", [0, -100])
def test_a_total_of_zero_or_less_is_rejected(authenticated_client, volume):
    response = authenticated_client.post("/flights/preview", json={**BODY, "contracted_impressions": volume})

    assert response.status_code == 422


def test_a_request_without_a_token_is_unauthenticated(client):
    assert client.post("/flights/preview", json=BODY).status_code == 401


def test_a_user_without_the_operations_role_is_forbidden(authenticated_client_no_operations_role):
    response = authenticated_client_no_operations_role.post("/flights/preview", json=BODY)

    assert response.status_code == 403
    assert response.json()["code"] == "missing_role"


def test_a_preview_stores_nothing(authenticated_client, test_db_session):
    records = (PurchaseOrderRecord, CampaignRecord, CampaignPeriodRecord, CampaignLineRecord, CampaignLinePeriodRecord)
    before = [test_db_session.scalar(select(func.count()).select_from(record)) for record in records]

    assert authenticated_client.post("/flights/preview", json=BODY).status_code == 200

    assert [test_db_session.scalar(select(func.count()).select_from(record)) for record in records] == before
