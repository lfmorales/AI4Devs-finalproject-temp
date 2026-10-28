"""The demonstration data shows the three states of the margin through GET /margin."""

from datetime import date
from decimal import Decimal

import pytest

from app.presentation.dependencies import providers
from scripts.seed_margin_demo import CLOSED_NAME, NO_PRICE_NAME, RUNNING_NAME, main

TODAY = date(2026, 10, 28)  # as_of is 27 October


@pytest.fixture
def demo(client_for_roles, test_db_session):
    assert main([], out=lambda line: None, session_factory=lambda: test_db_session, today=TODAY) == 0
    client = client_for_roles("finance")
    client.app.dependency_overrides[providers.get_today] = lambda: TODAY
    return client


def _by_campaign(body: dict) -> dict[str, dict]:
    return {campaign["name"]: campaign for campaign in body["campaigns"]}


def _states(campaign: dict) -> list[str]:
    return [flight["state"] for line in campaign["lines"] for flight in line["flights"]]


def test_before_closing_the_previous_month_is_pending_close_and_the_others_are_running(demo):
    campaigns = _by_campaign(demo.get("/margin").json())

    assert set(campaigns) == {CLOSED_NAME, RUNNING_NAME, NO_PRICE_NAME}
    assert _states(campaigns[CLOSED_NAME]) == ["pending_close"]
    assert _states(campaigns[RUNNING_NAME]) == ["running"]  # the November flight has not started
    assert _states(campaigns[NO_PRICE_NAME]) == ["running"]


def test_after_closing_the_previous_month_the_first_campaign_is_closed(demo):
    assert demo.post("/margin/closings", json={"year": 2026, "month": 9}).json()["closed"] == 1

    campaigns = _by_campaign(demo.get("/margin").json())

    assert _states(campaigns[CLOSED_NAME]) == ["closed"]
    assert _states(campaigns[RUNNING_NAME]) == ["running"]
    assert _states(campaigns[NO_PRICE_NAME]) == ["running"]


def test_the_three_states_show_up_together_in_one_read(demo):
    demo.post("/margin/closings", json={"year": 2026, "month": 9})

    flights = [f for c in demo.get("/margin").json()["campaigns"] for l in c["lines"] for f in l["flights"]]

    assert {flight["state"] for flight in flights} == {"closed", "running"}


def test_every_demo_flight_has_a_margin_other_than_zero(demo):
    flights = [f for c in demo.get("/margin").json()["campaigns"] for l in c["lines"] for f in l["flights"]]

    assert flights and all(Decimal(flight["margin"]) != 0 for flight in flights)


def test_the_closed_campaign_is_profitable_and_the_running_one_has_a_negative_margin(demo):
    campaigns = _by_campaign(demo.get("/margin").json())

    closed = campaigns[CLOSED_NAME]["lines"][0]["flights"][0]
    running = campaigns[RUNNING_NAME]["lines"][0]["flights"][0]
    assert Decimal(closed["margin"]) > 0 and closed["below_cost"] is False
    assert Decimal(running["media_cost"]) > Decimal(running["revenue"]) > 0
    assert running["below_cost"] is True and running["zero_sale"] is False


def test_the_campaign_without_a_price_has_no_revenue_no_rebate_and_zero_sale(demo):
    campaigns = _by_campaign(demo.get("/margin").json())

    flight = campaigns[NO_PRICE_NAME]["lines"][0]["flights"][0]
    assert (flight["revenue"], flight["rebate"]) == ("0.00", "0.00")
    assert Decimal(flight["media_cost"]) > 0 and Decimal(flight["platform_cost"]) > 0
    assert flight["zero_sale"] is True and flight["margin_pct"] is None
    assert campaigns[NO_PRICE_NAME]["zero_sale"] is True


def test_the_flat_example_rebate_applies_to_the_priced_campaigns(demo):
    campaigns = _by_campaign(demo.get("/margin").json())

    for name in (CLOSED_NAME, RUNNING_NAME):
        flight = campaigns[name]["lines"][0]["flights"][0]
        assert Decimal(flight["rebate"]) > 0
        assert flight["rates"]["rebate_step"] == 6


def test_running_the_command_again_does_not_change_what_the_margin_shows(demo, test_db_session):
    before = demo.get("/margin").json()

    assert main([], out=lambda line: None, session_factory=lambda: test_db_session, today=TODAY) == 0

    assert demo.get("/margin").json() == before
