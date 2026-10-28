"""GET /margin returns the sale of the whole flight and the days behind a running figure, at every level."""

from datetime import date
from decimal import Decimal

from app.domain.services.flight_margin import round_amount
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import add_line_to_campaign, insert_campaign_line, replace_flights
from tests.fixtures.margin_data import set_volume

SEPTEMBER_FIRST = date(2026, 9, 1)  # as_of is 31 August: August is over
AUGUST_11 = date(2026, 8, 11)       # as_of is 10 August: August is running


def _client(client_for_roles, today: date):
    client = client_for_roles("finance")
    client.app.dependency_overrides[providers.get_today] = lambda: today
    return client


def _get(client) -> dict:
    response = client.get("/margin")
    assert response.status_code == 200, response.text
    return response.json()


def _flights(body: dict) -> list[dict]:
    return [f for c in body["campaigns"] for l in c["lines"] for f in l["flights"]]


def test_a_running_flight_returns_the_whole_sale_and_fewer_accrued_days_than_window_days(client_for_roles, test_db_session):
    insert_campaign_line(test_db_session)

    (flight,) = _flights(_get(_client(client_for_roles, AUGUST_11)))

    assert flight["state"] == "running"
    assert flight["contracted_revenue"] == "5000.00"
    assert Decimal(flight["revenue"]) == round_amount(Decimal("5000") * 10 / 31)
    assert (flight["accrued_days"], flight["window_days"]) == (10, 31)
    assert flight["accrued_days"] < flight["window_days"]


def test_a_pending_close_flight_accrues_all_of_it(client_for_roles, test_db_session):
    insert_campaign_line(test_db_session)

    (flight,) = _flights(_get(_client(client_for_roles, SEPTEMBER_FIRST)))

    assert flight["state"] == "pending_close"
    assert flight["revenue"] == flight["contracted_revenue"] == "5000.00"
    assert flight["accrued_days"] == flight["window_days"] == 31


def test_a_closed_flight_accrues_all_of_it_and_closing_changes_none_of_the_three(client_for_roles, test_db_session):
    insert_campaign_line(test_db_session)
    client = _client(client_for_roles, SEPTEMBER_FIRST)
    (before,) = _flights(_get(client))
    assert client.post("/margin/closings", json={"year": 2026, "month": 8}).status_code == 200

    (after,) = _flights(_get(client))

    assert after["state"] == "closed"
    assert after["revenue"] == after["contracted_revenue"] == "5000.00"
    assert after["accrued_days"] == after["window_days"] == 31
    for field in ("contracted_revenue", "accrued_days", "window_days", "revenue"):
        assert after[field] == before[field]


def test_a_line_without_a_price_has_a_contracted_revenue_of_zero(client_for_roles, test_db_session):
    line_id = insert_campaign_line(test_db_session)
    set_volume(test_db_session, line_id, 500_000, "0.00")

    (flight,) = _flights(_get(_client(client_for_roles, AUGUST_11)))

    assert flight["contracted_revenue"] == "0.00" and flight["revenue"] == "0.00"
    assert flight["zero_sale"] is True and flight["accrued_days"] == 10


def test_every_level_adds_the_contracted_revenue_of_the_flights_below(client_for_roles, test_db_session):
    first = insert_campaign_line(test_db_session, start_date=date(2026, 8, 1), end_date=date(2026, 9, 30))
    replace_flights(test_db_session, first, [(date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), date(2026, 9, 30))])
    second = add_line_to_campaign(test_db_session, first, 2)
    set_volume(test_db_session, second, 300_000, "0.00")
    client = _client(client_for_roles, SEPTEMBER_FIRST)
    client.post("/margin/closings", json={"year": 2026, "month": 8})
    client.app.dependency_overrides[providers.get_today] = lambda: date(2026, 9, 11)

    body = _get(client)

    campaign = body["campaigns"][0]
    for line in campaign["lines"]:
        assert Decimal(line["totals"]["contracted_revenue"]) == sum(Decimal(f["contracted_revenue"]) for f in line["flights"])
    assert Decimal(campaign["totals"]["contracted_revenue"]) == sum(Decimal(l["totals"]["contracted_revenue"]) for l in campaign["lines"])
    assert body["totals"]["contracted_revenue"] == campaign["totals"]["contracted_revenue"]
    assert {f["state"] for f in _flights(body)} == {"closed", "running"}
    # The running September flight accrues less than it contracted, so the totals' revenue is below their contracted revenue.
    assert Decimal(body["totals"]["revenue"]) < Decimal(body["totals"]["contracted_revenue"])
    assert all(isinstance(f["accrued_days"], int) and isinstance(f["window_days"], int) for f in _flights(body))
