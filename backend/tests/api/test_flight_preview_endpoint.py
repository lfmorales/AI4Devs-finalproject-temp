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
