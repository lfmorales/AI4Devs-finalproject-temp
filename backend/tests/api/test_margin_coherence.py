"""Reading before closing and reading after closing give the same figures, to the cent; a closed month does not move.

One campaign, three flights of three different lines in two months, two of them starting on the same day, all
in one holding group so that the rebate counter links them.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.infrastructure.persistence.models.margin import PlatformRateSettingRecord
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import (
    add_line_to_campaign,
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    insert_user,
    replace_flights,
)
from tests.fixtures.margin_data import add_schedule, group_of, set_rate, set_volume

JULY = (date(2026, 7, 1), date(2026, 7, 31))
AUGUST = (date(2026, 8, 1), date(2026, 8, 31))
AMOUNTS = ("revenue", "media_cost", "rebate", "platform_cost", "margin")


@pytest.fixture
def scenario(client_for_roles, test_db_session):
    session = test_db_session
    line_a = insert_campaign_line(session, start_date=date(2026, 7, 1), end_date=date(2026, 8, 31))
    line_b = add_line_to_campaign(session, line_a, 2)
    line_c = add_line_to_campaign(session, line_a, 3)
    replace_flights(session, line_a, [JULY])
    replace_flights(session, line_b, [JULY])      # starts the same day as line A's flight
    replace_flights(session, line_c, [AUGUST])
    set_volume(session, line_a, 6_000_000)        # 30,000 EUR
    set_volume(session, line_b, 12_000_000)       # 60,000 EUR
    set_volume(session, line_c, 6_000_000)        # 30,000 EUR: it crosses the 100,000 cut of the counter
    schedule_id = add_schedule(session, group_of(session, line_a), ("0", "100000", "0.15"), ("100000", None, "0.2"))
    batch = insert_ingestion_batch(session)
    insert_delivery(session, line_a, date(2026, 7, 10), 1_234_567, batch, Decimal("812.345678"))
    insert_delivery(session, line_b, date(2026, 7, 20), 7_654_321, batch, Decimal("2468.135791"))
    insert_delivery(session, line_c, date(2026, 8, 15), 3_333_333, batch, Decimal("999.999999"))
    user_id = insert_user(session, "platform-rate-author@example.com")
    client = client_for_roles("finance")
    client.app.dependency_overrides[providers.get_today] = lambda: date(2026, 9, 1)
    return client, schedule_id, user_id


def _by_flight(body: dict) -> dict[int, dict]:
    return {f["flight_id"]: f for c in body["campaigns"] for l in c["lines"] for f in l["flights"]}


def _amounts(flight: dict) -> tuple[str, ...]:
    return tuple(flight[name] for name in AMOUNTS)


def test_the_figures_read_before_closing_are_the_figures_closing_freezes(scenario):
    client, _, _ = scenario

    before = _by_flight(client.get("/margin").json())
    assert len(before) == 3
    assert {f["state"] for f in before.values()} == {"pending_close"}
    assert all(f["provisional"] for f in before.values())

    assert client.post("/margin/closings", json={"year": 2026, "month": 7}).json()["closed"] == 2
    assert client.post("/margin/closings", json={"year": 2026, "month": 8}).json()["closed"] == 1
    after = _by_flight(client.get("/margin").json())

    assert {f["state"] for f in after.values()} == {"closed"}
    assert not any(f["provisional"] for f in after.values())
    assert set(after) == set(before)
    for flight_id, flight in after.items():
        assert _amounts(flight) == _amounts(before[flight_id]), flight_id
        assert Decimal(flight["rates"]["platform_rate"]) == Decimal(before[flight_id]["rates"]["platform_rate"])
        assert abs(Decimal(flight["rates"]["effective_rebate_rate"]) - Decimal(before[flight_id]["rates"]["effective_rebate_rate"])) < Decimal("1e-11")
        assert flight["rates"]["rebate_step"] == before[flight_id]["rates"]["rebate_step"]


def test_a_filter_does_not_change_the_figures_of_a_pending_flight(scenario):
    """August's flight depends on July's, which the month filter hides: its figures must not change."""
    client, _, _ = scenario

    everything = _by_flight(client.get("/margin").json())
    only_august = _by_flight(client.get("/margin", params={"month": 8}).json())

    (flight_id, flight), = only_august.items()
    assert _amounts(flight) == _amounts(everything[flight_id])
    assert flight["rebate"] != "4500.00"  # not priced as if it were the first flight of its counter


def test_the_counter_links_the_flights_in_order(scenario):
    client, _, _ = scenario

    flights = sorted(_by_flight(client.get("/margin").json()).values(), key=lambda f: (f["flight_start"], f["flight_id"]))

    # A: 30,000 at 15 %; B: 60,000 at 15 %; C: 30,000 from 90,000, of which 10,000 at 15 % and 20,000 at 20 %.
    assert [f["rebate"] for f in flights] == ["4500.00", "9000.00", "5500.00"]


def test_after_closing_a_change_of_schedule_or_platform_rate_does_not_move_the_closed_months(scenario, test_db_session):
    client, schedule_id, user_id = scenario
    client.post("/margin/closings", json={"year": 2026, "month": 7})
    client.post("/margin/closings", json={"year": 2026, "month": 8})
    closed = _by_flight(client.get("/margin").json())

    set_rate(test_db_session, schedule_id, "0.90")
    test_db_session.add(PlatformRateSettingRecord(level="system", rate_per_thousand=Decimal("9.00"), created_by=user_id))
    test_db_session.flush()
    again = _by_flight(client.get("/margin").json())
    client.post("/margin/closings", json={"year": 2026, "month": 7})

    assert again == closed
    assert _by_flight(client.get("/margin").json()) == closed


def test_a_change_of_schedule_does_move_a_flight_that_is_not_closed_yet(scenario, test_db_session):
    client, schedule_id, _ = scenario
    before = _by_flight(client.get("/margin").json())

    set_rate(test_db_session, schedule_id, "0.90")
    after = _by_flight(client.get("/margin").json())

    assert {f["state"] for f in after.values()} == {"pending_close"}
    assert any(_amounts(after[i]) != _amounts(before[i]) for i in before)


def test_closing_july_alone_leaves_august_pending_with_the_same_figures(scenario):
    client, _, _ = scenario
    before = _by_flight(client.get("/margin").json())

    client.post("/margin/closings", json={"year": 2026, "month": 7})
    after = _by_flight(client.get("/margin").json())

    assert sorted(f["state"] for f in after.values()) == ["closed", "closed", "pending_close"]
    for flight_id, flight in after.items():
        assert _amounts(flight) == _amounts(before[flight_id])
