"""The demonstration data shows the three states of the margin through GET /margin."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.presentation.dependencies import providers
from scripts.seed_margin_demo import (
    CLOSED_NAME,
    DEAL_NAME,
    DOOH_NAME,
    NEGATIVE_NAME,
    NO_PRICE_NAME,
    RUNNING_NAME,
    main,
)

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

    # The masters of the test database hold the real DOOH channel, the Equativ DSP and the Deal channel, so the DOOH and
    # the Deal campaigns are there too.
    assert set(campaigns) == {CLOSED_NAME, RUNNING_NAME, NEGATIVE_NAME, NO_PRICE_NAME, DOOH_NAME, DEAL_NAME}
    assert _states(campaigns[DEAL_NAME]) == ["pending_close", "running"]
    assert _states(campaigns[CLOSED_NAME]) == ["pending_close"]
    assert _states(campaigns[RUNNING_NAME]) == ["running"]  # the November flight has not started
    assert _states(campaigns[NEGATIVE_NAME]) == ["running"]
    assert _states(campaigns[NO_PRICE_NAME]) == ["running"]
    assert _states(campaigns[DOOH_NAME]) == ["running"]


def test_after_closing_the_previous_month_the_first_campaign_is_closed(demo):
    # The closed campaign's flight and the Deal's September flight: Equativ has loaded 30 September, so it closes too.
    assert demo.post("/margin/closings", json={"year": 2026, "month": 9}).json()["closed"] == 2

    campaigns = _by_campaign(demo.get("/margin").json())

    assert _states(campaigns[CLOSED_NAME]) == ["closed"]
    assert _states(campaigns[RUNNING_NAME]) == ["running"]
    assert _states(campaigns[NEGATIVE_NAME]) == ["running"]
    assert _states(campaigns[NO_PRICE_NAME]) == ["running"]


def test_the_three_states_show_up_together_in_one_read(demo):
    demo.post("/margin/closings", json={"year": 2026, "month": 9})

    flights = [f for c in demo.get("/margin").json()["campaigns"] for l in c["lines"] for f in l["flights"]]

    assert {flight["state"] for flight in flights} == {"closed", "running"}


def test_every_demo_flight_has_a_margin_other_than_zero(demo):
    flights = [f for c in demo.get("/margin").json()["campaigns"] for l in c["lines"] for f in l["flights"]]

    assert flights and all(Decimal(flight["margin"]) != 0 for flight in flights)


def test_the_closed_and_the_running_campaigns_are_profitable_and_the_new_one_has_a_negative_margin(demo):
    campaigns = _by_campaign(demo.get("/margin").json())

    closed = campaigns[CLOSED_NAME]["lines"][0]["flights"][0]
    running = campaigns[RUNNING_NAME]["lines"][0]["flights"][0]
    negative = campaigns[NEGATIVE_NAME]["lines"][0]["flights"][0]
    assert Decimal(closed["margin"]) > 0 and closed["below_cost"] is False
    assert Decimal(running["margin"]) > 0 and running["below_cost"] is False and running["zero_sale"] is False
    assert Decimal("40") <= Decimal(running["margin_pct"]) <= Decimal("50")
    assert Decimal(negative["media_cost"]) > Decimal(negative["revenue"]) > 0
    assert Decimal(negative["margin"]) < 0 and negative["below_cost"] is True and negative["zero_sale"] is False


def test_the_campaign_without_a_price_has_no_revenue_no_rebate_and_zero_sale(demo):
    campaigns = _by_campaign(demo.get("/margin").json())

    flight = campaigns[NO_PRICE_NAME]["lines"][0]["flights"][0]
    assert (flight["revenue"], flight["rebate"]) == ("0.00", "0.00")
    assert Decimal(flight["media_cost"]) > 0 and Decimal(flight["platform_cost"]) > 0
    assert flight["zero_sale"] is True and flight["margin_pct"] is None
    assert campaigns[NO_PRICE_NAME]["zero_sale"] is True


def test_the_flat_example_rebate_applies_to_the_priced_campaigns(demo):
    campaigns = _by_campaign(demo.get("/margin").json())

    for name in (CLOSED_NAME, RUNNING_NAME, NEGATIVE_NAME):
        flight = campaigns[name]["lines"][0]["flights"][0]
        assert Decimal(flight["rebate"]) > 0
        assert flight["rates"]["rebate_step"] == 6


def test_running_the_command_again_does_not_change_what_the_margin_shows(demo, test_db_session):
    before = demo.get("/margin").json()

    assert main([], out=lambda line: None, session_factory=lambda: test_db_session, today=TODAY) == 0

    assert demo.get("/margin").json() == before


def test_the_dooh_campaign_reads_in_ots_with_decimals_and_fewer_impressions(demo: Any) -> None:
    campaigns = _by_campaign(demo.get("/margin").json())

    flight = campaigns[DOOH_NAME]["lines"][0]["flights"][0]
    assert flight["delivery_metric"] == "ots"
    assert Decimal(flight["delivered"]) > flight["delivered_impressions"] > 0
    assert Decimal(flight["delivered"]) != Decimal(flight["delivered"]).to_integral_value()
    assert {c["lines"][0]["flights"][0]["delivery_metric"] for n, c in campaigns.items() if n != DOOH_NAME} == {"impressions"}
    assert campaigns[DOOH_NAME]["totals"]["delivery_metric"] == "ots"


# ---------------------------------------------------------------- the Deal campaign: the worked example and a target

def _deal_flights(client: Any) -> list[dict[str, Any]]:
    campaigns = _by_campaign(client.get("/margin").json())
    return [flight for line in campaigns[DEAL_NAME]["lines"] for flight in line["flights"]]


def _worked_example(flight: dict[str, Any]) -> tuple[Any, ...]:
    return (
        flight["volume_commitment"], flight["contracted_revenue"], flight["revenue"], flight["gross_revenue"],
        flight["media_cost"], flight["rebate"], flight["platform_cost"], flight["margin"], flight["margin_pct"],
        flight["gross_differs_from_buyer_spend"], flight["data_cost_reported"],
    )


WORKED_EXAMPLE = (
    "target", "5000.00", "4400.00", "5500.00", "0.00", "550.00", "1100.00", "2750.00", "62.50", False, False,
)


def test_the_deal_september_flight_reproduces_the_worked_example_before_and_after_closing(demo: Any) -> None:
    september, _ = _deal_flights(demo)
    assert september["state"] == "pending_close"
    assert _worked_example(september) == WORKED_EXAMPLE

    demo.post("/margin/closings", json={"year": 2026, "month": 9})
    closed, _ = _deal_flights(demo)

    assert closed["state"] == "closed"
    assert _worked_example(closed) == WORKED_EXAMPLE


def test_the_deal_october_flight_runs_above_its_target_with_a_data_cost_and_no_pacing_warning(demo: Any) -> None:
    _, october = _deal_flights(demo)
    assert (october["state"], october["volume_commitment"], october["data_cost_reported"]) == ("running", "target", True)

    rows = [row for row in demo.get("/campaign-status").json() if row["campaign"]["name"] == DEAL_NAME]

    (row,) = rows
    assert (row["volume_commitment"], row["pacing"]["status"], row["pacing_flag"]) == ("target", "over_delivering", False)
    assert row["pacing"]["deviation"] > 0.1
