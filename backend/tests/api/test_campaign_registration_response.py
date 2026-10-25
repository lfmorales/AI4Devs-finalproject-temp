"""The registration response: lines carry their number, dates, total and flights, and no period of their own."""

LINE_FIELDS = {
    "id", "dsp_id", "channel_id", "format_id", "scope", "market_description", "contracted_impressions",
    "sale_cpm", "currency", "line_number", "start_date", "end_date", "flights",
}
FLIGHT_FIELDS = {
    "campaign_period_id", "period_year", "period_month", "flight_start", "flight_end", "contracted_impressions",
}


def _payload(**overrides):
    payload = {
        "name": "CAMP-RESPONSE", "display_name": "Response", "agency_id": 1, "advertiser_id": 1,
        "campaign_type_id": 1, "sector_id": 1, "sales_rep_id": 1,
        "start_date": "2026-08-01", "end_date": "2026-10-31",
        "order_reference": "PO-RESPONSE", "order_received_on": "2026-07-01",
        "lines": [{
            "dsp_id": 1, "channel_id": 1, "format_id": 1, "scope": "national", "market_description": "Spain",
            "contracted_impressions": 100, "sale_cpm": "5.00",
        }],
    }
    payload.update(overrides)
    return payload


def test_a_line_carries_its_number_dates_total_and_flights(authenticated_client):
    response = authenticated_client.post("/campaigns", json=_payload())

    assert response.status_code == 201, response.text
    line = response.json()["lines"][0]
    assert set(line) == LINE_FIELDS
    assert (line["line_number"], line["start_date"], line["end_date"]) == (1, "2026-08-01", "2026-10-31")
    assert line["contracted_impressions"] == 100


def test_a_flight_carries_its_period_month_window_and_volume(authenticated_client):
    data = authenticated_client.post("/campaigns", json=_payload()).json()

    flights = data["lines"][0]["flights"]
    assert all(set(flight) == FLIGHT_FIELDS for flight in flights)
    assert [(f["period_year"], f["period_month"], f["flight_start"], f["flight_end"], f["contracted_impressions"])
            for f in flights] == [
        (2026, 8, "2026-08-01", "2026-08-31", 34),
        (2026, 9, "2026-09-01", "2026-09-30", 32),
        (2026, 10, "2026-10-01", "2026-10-31", 34),
    ]


def test_the_periods_of_the_campaign_stay_in_the_response_as_its_calendar(authenticated_client):
    data = authenticated_client.post("/campaigns", json=_payload()).json()

    assert [(p["period_year"], p["period_month"]) for p in data["periods"]] == [(2026, 8), (2026, 9), (2026, 10)]
    period_by_month = {p["period_month"]: p["id"] for p in data["periods"]}
    assert all(f["campaign_period_id"] == period_by_month[f["period_month"]] for f in data["lines"][0]["flights"])


def test_no_field_of_the_response_is_a_period_of_the_line(authenticated_client):
    data = authenticated_client.post("/campaigns", json=_payload()).json()

    assert "campaign_period_id" not in data["lines"][0]
