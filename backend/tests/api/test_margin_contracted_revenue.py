"""GET /margin returns the sale of the whole flight and the days behind a running figure, at every level."""

from datetime import date
from decimal import Decimal

from app.domain.services.flight_margin import round_amount
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import (
    add_line_to_campaign,
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    replace_flights,
)
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


# ---------------------------------------------------------------- the volumes behind the amounts

VOLUMES = ("delivered_impressions", "contracted_impressions")


def _deliver(session, line_id: int, day: date, impressions: int) -> None:
    insert_delivery(session, line_id, day, impressions, insert_ingestion_batch(session), Decimal("10.00"))


def test_a_delivery_outside_the_flight_window_is_not_counted(client_for_roles, test_db_session):
    line_id = insert_campaign_line(test_db_session, start_date=date(2026, 8, 1), end_date=date(2026, 9, 30))
    replace_flights(test_db_session, line_id, [(date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), date(2026, 9, 30))])
    _deliver(test_db_session, line_id, date(2026, 7, 31), 111)   # before the first flight
    _deliver(test_db_session, line_id, date(2026, 8, 1), 1_000)  # first day of August
    _deliver(test_db_session, line_id, date(2026, 8, 31), 2_000)  # last day of August
    _deliver(test_db_session, line_id, date(2026, 9, 1), 4_000)  # first day of September, not August's
    client = _client(client_for_roles, date(2026, 9, 11))

    august, september = _flights(_get(client))

    assert august["delivered_impressions"] == 3_000
    assert september["delivered_impressions"] == 4_000


def test_the_three_states_carry_the_volumes_and_closing_changes_neither(client_for_roles, test_db_session):
    line_id = insert_campaign_line(test_db_session, start_date=date(2026, 8, 1), end_date=date(2026, 10, 31))
    replace_flights(test_db_session, line_id, [
        (date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), date(2026, 9, 30)), (date(2026, 10, 1), date(2026, 10, 31)),
    ])
    for day, impressions in ((date(2026, 8, 5), 100), (date(2026, 9, 5), 200), (date(2026, 10, 5), 400)):
        _deliver(test_db_session, line_id, day, impressions)
    client = _client(client_for_roles, date(2026, 10, 11))
    before_closing = _flights(_get(client))
    client.post("/margin/closings", json={"year": 2026, "month": 8})

    flights = _flights(_get(client))

    assert [f["state"] for f in flights] == ["closed", "pending_close", "running"]
    assert [f["delivered_impressions"] for f in flights] == [100, 200, 400]
    assert [f["state"] for f in before_closing] == ["pending_close", "pending_close", "running"]
    for name in VOLUMES:
        assert [f[name] for f in flights] == [f[name] for f in before_closing]
    assert all(isinstance(f[name], int) for f in flights for name in VOLUMES)


def test_a_line_without_a_price_reports_its_volumes(client_for_roles, test_db_session):
    line_id = insert_campaign_line(test_db_session)
    set_volume(test_db_session, line_id, 500_000, "0.00")
    _deliver(test_db_session, line_id, date(2026, 8, 5), 400_000)

    (flight,) = _flights(_get(_client(client_for_roles, AUGUST_11)))

    assert flight["zero_sale"] is True
    assert (flight["delivered_impressions"], flight["contracted_impressions"]) == (400_000, 500_000)


def test_the_volumes_add_exactly_at_every_level_with_several_flights(client_for_roles, test_db_session):
    first = insert_campaign_line(test_db_session, start_date=date(2026, 8, 1), end_date=date(2026, 9, 30))
    replace_flights(test_db_session, first, [(date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), date(2026, 9, 30))])
    second = add_line_to_campaign(test_db_session, first, 2)
    set_volume(test_db_session, second, 300_001, "0.00")
    for line_id, day, impressions in ((first, date(2026, 8, 3), 111), (first, date(2026, 9, 3), 222), (second, date(2026, 8, 4), 333)):
        _deliver(test_db_session, line_id, day, impressions)

    body = _get(_client(client_for_roles, date(2026, 9, 11)))

    campaign = body["campaigns"][0]
    for name in VOLUMES:
        for line in campaign["lines"]:
            assert line["totals"][name] == sum(f[name] for f in line["flights"])
        assert campaign["totals"][name] == sum(line["totals"][name] for line in campaign["lines"])
        assert body["totals"][name] == campaign["totals"][name] == sum(f[name] for f in _flights(body))
    assert body["totals"]["delivered_impressions"] == 111 + 222 + 333
