"""The spec's worked examples through the whole stack: schedule created by API, closing, and the margin read."""

from datetime import date
from decimal import Decimal

import pytest

from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import insert_campaign_line, insert_delivery, insert_ingestion_batch, replace_flights
from tests.fixtures.margin_data import group_of, set_volume


@pytest.fixture
def finance(client_for_roles):
    return client_for_roles("finance")


def _flat_schedule(client, group_id: int, rate: str) -> None:
    response = client.post("/margin/rebate-schedules", json={
        "holding_group_id": group_id, "valid_from": "2026-01-01",
        "brackets": [{"lower": "0", "upper": None, "rate": rate}],
    })
    assert response.status_code == 201, response.text


def _only_flight(body: dict) -> dict:
    (flight,) = [f for c in body["campaigns"] for l in c["lines"] for f in l["flights"]]
    return flight


def test_a_closed_month_gives_the_margin_of_the_specs_worked_example(finance, test_db_session):
    """726,202 impressions at 5.00 EUR; 25 % rebate; 700,000 delivered at 1.00 EUR per thousand; media cost 1,200.00.

    The media cost is a placeholder: real cost only exists in Adform.
    """
    line_id = insert_campaign_line(test_db_session)
    set_volume(test_db_session, line_id, 726_202, "5.00")
    insert_delivery(test_db_session, line_id, date(2026, 8, 10), 700_000, insert_ingestion_batch(test_db_session), Decimal("1200.00"))
    _flat_schedule(finance, group_of(test_db_session, line_id), "0.25")
    finance.app.dependency_overrides[providers.get_today] = lambda: date(2026, 9, 1)

    assert finance.post("/margin/closings", json={"year": 2026, "month": 8}).json()["closed"] == 1
    body = finance.get("/margin").json()
    flight = _only_flight(body)

    assert flight["state"] == "closed" and flight["provisional"] is False
    assert (flight["revenue"], flight["media_cost"], flight["rebate"], flight["platform_cost"], flight["margin"]) == (
        "3631.01", "1200.00", "907.75", "700.00", "823.26")
    for totals in (body["campaigns"][0]["lines"][0]["totals"], body["campaigns"][0]["totals"], body["totals"]):
        assert (totals["revenue"], totals["media_cost"], totals["rebate"], totals["platform_cost"], totals["margin"]) == (
            "3631.01", "1200.00", "907.75", "700.00", "823.26")


def test_the_same_figures_are_read_before_the_month_is_closed(finance, test_db_session):
    line_id = insert_campaign_line(test_db_session)
    set_volume(test_db_session, line_id, 726_202, "5.00")
    insert_delivery(test_db_session, line_id, date(2026, 8, 10), 700_000, insert_ingestion_batch(test_db_session), Decimal("1200.00"))
    _flat_schedule(finance, group_of(test_db_session, line_id), "0.25")
    finance.app.dependency_overrides[providers.get_today] = lambda: date(2026, 9, 1)

    flight = _only_flight(finance.get("/margin").json())

    assert flight["state"] == "pending_close" and flight["provisional"] is True
    assert flight["margin"] == "823.26"


def test_a_running_flight_ten_days_into_thirty_is_pro_rated_and_provisional(finance, test_db_session):
    """300,000 impressions at 5.00 EUR over 1-30 September; a flat 20 % rebate; 90,000 delivered, media cost 150.00.

    On the 10th (as_of): revenue 1,500.00 x 10 / 30 = 500.00; rebate 300.00 x 10 / 30 = 100.00; platform
    90,000 / 1000 x 1.00 = 90.00; margin 500.00 - 150.00 - 100.00 - 90.00 = 160.00.
    """
    line_id = insert_campaign_line(test_db_session, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30))
    replace_flights(test_db_session, line_id, [(date(2026, 9, 1), date(2026, 9, 30))])
    set_volume(test_db_session, line_id, 300_000, "5.00")
    insert_delivery(test_db_session, line_id, date(2026, 9, 5), 90_000, insert_ingestion_batch(test_db_session), Decimal("150.00"))
    _flat_schedule(finance, group_of(test_db_session, line_id), "0.20")
    finance.app.dependency_overrides[providers.get_today] = lambda: date(2026, 9, 11)

    body = finance.get("/margin").json()
    flight = _only_flight(body)

    assert flight["state"] == "running" and flight["provisional"] is True
    assert (flight["revenue"], flight["media_cost"], flight["rebate"], flight["platform_cost"], flight["margin"]) == (
        "500.00", "150.00", "100.00", "90.00", "160.00")
    assert body["totals"]["provisional"] is True
