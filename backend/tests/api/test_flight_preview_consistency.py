"""For the same input, the preview shows exactly the flights the registration stores."""

import pytest

FLIGHT_FIELDS = ("period_year", "period_month", "flight_start", "flight_end", "contracted_impressions")

CASES = [
    pytest.param("2026-08-01", "2026-10-31", {}, 100, id="inherited-three-months"),
    pytest.param("2026-08-15", "2026-12-20", {}, 1_000_003, id="mid-month-start-and-end"),
    pytest.param("2026-08-01", "2026-10-31", {"start_date": "2026-09-10", "end_date": "2026-10-05"}, 1000, id="own-dates"),
    pytest.param("2026-08-01", "2026-10-31", {"end_date": "2026-09-20"}, 999, id="ends-early"),
    pytest.param("2026-08-01", "2026-10-31", {"start_date": "2026-10-31", "end_date": "2026-10-31"}, 7, id="one-day"),
    pytest.param("2026-08-05", "2026-08-20", {}, 12345, id="single-month-campaign"),
    pytest.param("2026-11-20", "2027-02-10", {}, 50_000, id="across-the-year"),
]


@pytest.mark.parametrize(("campaign_start", "campaign_end", "line_dates", "total"), CASES)
def test_the_preview_flights_are_identical_to_the_registered_ones(
    authenticated_client, campaign_start, campaign_end, line_dates, total
):
    preview = authenticated_client.post("/flights/preview", json={
        "campaign_start_date": campaign_start, "campaign_end_date": campaign_end,
        "contracted_impressions": total, **line_dates,
    })
    registration = authenticated_client.post("/campaigns", json={
        "name": "CAMP-CONSISTENCY", "display_name": "Consistency", "agency_id": 1, "advertiser_id": 1,
        "campaign_type_id": 1, "sector_id": 1, "sales_rep_id": 1,
        "start_date": campaign_start, "end_date": campaign_end,
        "order_reference": "PO-CONSISTENCY", "order_received_on": "2026-07-01",
        "lines": [{
            "dsp_id": 1, "channel_id": 1, "format_id": 1, "scope": "national", "market_description": "Spain",
            "contracted_impressions": total, "sale_cpm": "5.00", **line_dates,
        }],
    })

    assert preview.status_code == 200, preview.text
    assert registration.status_code == 201, registration.text
    registered_line = registration.json()["lines"][0]
    assert [{field: flight[field] for field in FLIGHT_FIELDS} for flight in registered_line["flights"]] == \
        preview.json()["flights"]
    assert (preview.json()["start_date"], preview.json()["end_date"]) == \
        (registered_line["start_date"], registered_line["end_date"])


def test_the_preview_and_the_registration_reject_the_same_input_with_the_same_code(authenticated_client):
    line_dates = {"start_date": "2026-07-01"}
    preview = authenticated_client.post("/flights/preview", json={
        "campaign_start_date": "2026-08-01", "campaign_end_date": "2026-10-31",
        "contracted_impressions": 100, **line_dates,
    })
    registration = authenticated_client.post("/campaigns", json={
        "name": "CAMP-CONSISTENCY-ERR", "display_name": "Consistency", "agency_id": 1, "advertiser_id": 1,
        "campaign_type_id": 1, "sector_id": 1, "sales_rep_id": 1,
        "start_date": "2026-08-01", "end_date": "2026-10-31",
        "order_reference": "PO-CONSISTENCY-ERR", "order_received_on": "2026-07-01",
        "lines": [{
            "dsp_id": 1, "channel_id": 1, "format_id": 1, "scope": "national", "market_description": "Spain",
            "contracted_impressions": 100, "sale_cpm": "5.00", **line_dates,
        }],
    })

    assert preview.status_code == registration.status_code == 422
    assert preview.json() == registration.json()
