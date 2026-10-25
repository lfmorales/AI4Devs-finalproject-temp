"""Registering over several months through the API: lines, flights, volume splits and rejections."""

import pytest
from sqlalchemy import func, select

from app.infrastructure.persistence.models import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
    PurchaseOrderRecord,
)


def _line(**overrides):
    line = {
        "dsp_id": 1, "channel_id": 1, "format_id": 1, "scope": "national", "market_description": "Spain",
        "contracted_impressions": 1000, "sale_cpm": "5.00",
    }
    line.update(overrides)
    return line


def _payload(lines, start="2026-08-01", end="2026-10-31", name="CAMP-FLIGHTS"):
    return {
        "name": name, "display_name": name, "agency_id": 1, "advertiser_id": 1, "campaign_type_id": 1,
        "sector_id": 1, "sales_rep_id": 1, "start_date": start, "end_date": end,
        "order_reference": f"PO-{name}", "order_received_on": "2026-07-01", "lines": lines,
    }


def _stored_counts(session) -> dict[str, int]:
    return {
        record.__tablename__: session.scalar(select(func.count()).select_from(record))
        for record in (
            PurchaseOrderRecord, CampaignRecord, CampaignPeriodRecord, CampaignLineRecord, CampaignLinePeriodRecord
        )
    }


def _volumes(entries):
    return [{"year": year, "month": month, "volume": volume} for year, month, volume in entries]


def test_one_line_over_three_months_is_one_line_with_three_flights_that_add_up(authenticated_client):
    response = authenticated_client.post("/campaigns", json=_payload([_line(contracted_impressions=1000)]))

    assert response.status_code == 201, response.text
    lines = response.json()["lines"]
    assert len(lines) == 1 and len(lines[0]["flights"]) == 3
    assert sum(f["contracted_impressions"] for f in lines[0]["flights"]) == lines[0]["contracted_impressions"] == 1000


def test_two_lines_over_two_months_are_two_lines_of_two_flights_with_no_duplicates(authenticated_client, test_db_session):
    payload = _payload([_line(), _line(format_id=2)], end="2026-09-30")

    response = authenticated_client.post("/campaigns", json=payload)

    assert response.status_code == 201, response.text
    assert [len(line["flights"]) for line in response.json()["lines"]] == [2, 2]
    assert [line["line_number"] for line in response.json()["lines"]] == [1, 2]
    stored = _stored_counts(test_db_session)
    assert (stored["campaign_periods"], stored["campaign_lines"], stored["campaign_line_periods"]) == (2, 2, 4)


def test_a_line_in_one_month_has_one_flight_with_the_total(authenticated_client):
    response = authenticated_client.post(
        "/campaigns", json=_payload([_line(contracted_impressions=777)], end="2026-08-31")
    )

    assert response.status_code == 201, response.text
    assert [f["contracted_impressions"] for f in response.json()["lines"][0]["flights"]] == [777]


def test_a_line_starting_mid_campaign_and_one_ending_early_only_have_the_flights_that_intersect(authenticated_client):
    lines = [_line(start_date="2026-09-10"), _line(format_id=2, end_date="2026-08-20")]

    response = authenticated_client.post("/campaigns", json=_payload(lines))

    assert response.status_code == 201, response.text
    late, early = response.json()["lines"]
    assert [(f["period_month"], f["flight_start"]) for f in late["flights"]] == [(9, "2026-09-10"), (10, "2026-10-01")]
    assert [(f["period_month"], f["flight_end"]) for f in early["flights"]] == [(8, "2026-08-20")]
    assert early["flights"][0]["contracted_impressions"] == early["contracted_impressions"]


def test_two_lines_with_different_formats_can_share_a_month(authenticated_client, test_db_session):
    lines = [_line(format_id=1), _line(format_id=2), _line(format_id=3, sale_cpm="25.00")]

    response = authenticated_client.post("/campaigns", json=_payload(lines, end="2026-08-31"))

    assert response.status_code == 201, response.text
    assert [line["format_id"] for line in response.json()["lines"]] == [1, 2, 3]
    period_ids = {line["flights"][0]["campaign_period_id"] for line in response.json()["lines"]}
    assert len(period_ids) == 1
    assert _stored_counts(test_db_session)["campaign_line_periods"] == 3


def test_valid_explicit_monthly_volumes_are_used_as_given(authenticated_client):
    line = _line(monthly_volumes=_volumes([(2026, 8, 100), (2026, 9, 300), (2026, 10, 600)]))

    response = authenticated_client.post("/campaigns", json=_payload([line]))

    assert response.status_code == 201, response.text
    assert [f["contracted_impressions"] for f in response.json()["lines"][0]["flights"]] == [100, 300, 600]


@pytest.mark.parametrize(("entries", "code"), [
    ([(2026, 8, 500), (2026, 9, 500)], "flight_volumes_incomplete"),
    ([(2026, 8, 400), (2026, 9, 300), (2026, 9, 300), (2026, 10, 300)], "flight_volumes_incomplete"),
    ([(2026, 8, 300), (2026, 9, 300), (2026, 10, 300), (2026, 11, 100)], "flight_volumes_incomplete"),
    ([(2026, 8, 300), (2026, 9, 300), (2026, 10, 401)], "flight_volumes_mismatch"),
    ([(2026, 8, 300), (2026, 9, 300), (2026, 10, 399)], "flight_volumes_mismatch"),
    ([(2026, 8, 0), (2026, 9, 500), (2026, 10, 500)], "flight_volume_not_positive"),
    ([(2026, 8, -100), (2026, 9, 600), (2026, 10, 500)], "flight_volume_not_positive"),
])
def test_invalid_explicit_volumes_are_rejected_and_nothing_is_stored(authenticated_client, test_db_session, entries, code):
    before = _stored_counts(test_db_session)

    response = authenticated_client.post("/campaigns", json=_payload([_line(monthly_volumes=_volumes(entries))]))

    assert response.status_code == 422
    assert response.json()["code"] == code and set(response.json()) == {"code", "message"}
    assert _stored_counts(test_db_session) == before


@pytest.mark.parametrize("dates", [
    {"start_date": "2026-07-31"},
    {"end_date": "2026-11-01"},
    {"start_date": "2026-07-01", "end_date": "2026-12-31"},
])
def test_line_dates_outside_the_campaign_are_rejected(authenticated_client, test_db_session, dates):
    before = _stored_counts(test_db_session)

    response = authenticated_client.post("/campaigns", json=_payload([_line(**dates)]))

    assert response.status_code == 422
    assert response.json()["code"] == "line_dates_outside_campaign"
    assert _stored_counts(test_db_session) == before


def test_inverted_line_dates_are_rejected(authenticated_client, test_db_session):
    before = _stored_counts(test_db_session)

    response = authenticated_client.post(
        "/campaigns", json=_payload([_line(start_date="2026-09-10", end_date="2026-09-09")])
    )

    assert response.status_code == 422
    assert response.json()["code"] == "line_dates_invalid"
    assert _stored_counts(test_db_session) == before


def test_a_start_after_the_campaign_end_with_no_end_is_rejected_as_invalid_dates(authenticated_client):
    response = authenticated_client.post("/campaigns", json=_payload([_line(start_date="2026-11-15")]))

    assert response.status_code == 422
    assert response.json()["code"] == "line_dates_invalid"


def test_a_total_too_small_for_its_flights_is_rejected_and_nothing_is_stored(authenticated_client, test_db_session):
    before = _stored_counts(test_db_session)

    response = authenticated_client.post("/campaigns", json=_payload([_line(contracted_impressions=2)]))

    assert response.status_code == 422
    assert response.json()["code"] == "volume_too_small_for_flights"
    assert _stored_counts(test_db_session) == before


def test_one_bad_line_among_good_ones_leaves_nothing_stored(authenticated_client, test_db_session):
    before = _stored_counts(test_db_session)
    lines = [_line(), _line(format_id=2), _line(format_id=3, end_date="2027-01-01")]

    response = authenticated_client.post("/campaigns", json=_payload(lines))

    assert response.status_code == 422
    assert _stored_counts(test_db_session) == before


def test_an_unknown_reference_on_a_later_line_leaves_nothing_stored(authenticated_client, test_db_session):
    before = _stored_counts(test_db_session)

    response = authenticated_client.post("/campaigns", json=_payload([_line(), _line(channel_id=9999)]))

    assert response.status_code == 400
    assert _stored_counts(test_db_session) == before
