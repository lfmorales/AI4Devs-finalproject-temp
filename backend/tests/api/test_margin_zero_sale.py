"""A line without a price through GET /margin: no revenue and no rebate, the cost remains, flagged "Sin venta"."""

from datetime import date
from decimal import Decimal

import pytest

from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import add_line_to_campaign, insert_campaign_line, insert_delivery, insert_ingestion_batch
from tests.fixtures.margin_data import add_schedule, group_of, set_volume


@pytest.fixture
def world(client_for_roles, test_db_session):
    """One campaign: a line without a price (cost 120.00, 400,000 delivered) and a priced sibling line."""
    free_line = insert_campaign_line(test_db_session)
    priced_line = add_line_to_campaign(test_db_session, free_line, 2)
    set_volume(test_db_session, free_line, 500_000, "0.00")
    set_volume(test_db_session, priced_line, 726_202, "5.00")
    add_schedule(test_db_session, group_of(test_db_session, free_line), ("0", None, "0.25"))
    batch = insert_ingestion_batch(test_db_session)
    insert_delivery(test_db_session, free_line, date(2026, 8, 10), 400_000, batch, Decimal("120.00"))
    insert_delivery(test_db_session, priced_line, date(2026, 8, 10), 700_000, batch, Decimal("1200.00"))
    client = client_for_roles("finance")
    client.app.dependency_overrides[providers.get_today] = lambda: date(2026, 9, 1)
    return client


def _lines(body: dict) -> dict[int, dict]:
    return {line["line_number"]: line for campaign in body["campaigns"] for line in campaign["lines"]}


def test_a_flight_without_a_price_has_no_revenue_no_rebate_and_a_margin_of_minus_its_cost(world):
    body = world.get("/margin").json()

    (free,) = _lines(body)[1]["flights"]
    assert (free["revenue"], free["rebate"], free["media_cost"], free["platform_cost"], free["margin"]) == (
        "0.00", "0.00", "120.00", "400.00", "-520.00")
    assert free["zero_sale"] is True and free["below_cost"] is True


def test_the_priced_sibling_is_not_zero_sale(world):
    (priced,) = _lines(world.get("/margin").json())[2]["flights"]

    assert priced["zero_sale"] is False
    assert priced["margin"] == "823.26"


def test_zero_sale_reaches_the_line_the_campaign_and_the_counts(world):
    body = world.get("/margin").json()
    lines = _lines(body)

    assert (lines[1]["zero_sale"], lines[2]["zero_sale"]) == (True, False)
    assert body["campaigns"][0]["zero_sale"] is True
    assert (lines[1]["totals"]["zero_sale_count"], lines[2]["totals"]["zero_sale_count"]) == (1, 0)
    assert body["campaigns"][0]["totals"]["zero_sale_count"] == 1
    assert body["totals"]["zero_sale_count"] == 1
    assert body["totals"]["below_cost_count"] == 1


def test_the_totals_keep_the_true_value_of_the_free_flight(world):
    body = world.get("/margin").json()

    assert body["totals"]["revenue"] == "3631.01"
    assert body["totals"]["margin"] == str(Decimal("823.26") + Decimal("-520.00"))


def test_the_free_line_adds_nothing_to_the_counter_and_is_the_same_after_closing(world):
    before = world.get("/margin").json()
    assert world.post("/margin/closings", json={"year": 2026, "month": 8}).json()["closed"] == 2
    after = world.get("/margin").json()

    (free,) = _lines(after)[1]["flights"]
    assert free["state"] == "closed" and free["zero_sale"] is True and free["rebate"] == "0.00"
    # The priced line is priced as if the free one were not in its counter: 25 % of 3,631.01.
    assert _lines(after)[2]["flights"][0]["rebate"] == "907.75"
    assert after["totals"]["margin"] == before["totals"]["margin"]


def test_a_line_without_revenue_has_no_percentage_and_the_levels_with_revenue_have_one(world):
    body = world.get("/margin").json()
    lines = _lines(body)

    (free,) = lines[1]["flights"]
    assert free["margin_pct"] is None and lines[1]["totals"]["margin_pct"] is None
    assert lines[2]["flights"][0]["margin_pct"] == "22.67"
    # The campaign and the report divide their own sums: (823.26 - 520.00) / 3,631.01.
    expected = str((Decimal("303.26") * 100 / Decimal("3631.01")).quantize(Decimal("0.01")))
    assert body["campaigns"][0]["totals"]["margin_pct"] == body["totals"]["margin_pct"] == expected


def test_a_campaign_made_only_of_free_lines_has_no_percentage_anywhere(client_for_roles, test_db_session):
    line_id = insert_campaign_line(test_db_session, campaign_name="Only free")
    set_volume(test_db_session, line_id, 500_000, "0.00")
    insert_delivery(test_db_session, line_id, date(2026, 8, 10), 400_000, insert_ingestion_batch(test_db_session), Decimal("120.00"))
    client = client_for_roles("finance")
    client.app.dependency_overrides[providers.get_today] = lambda: date(2026, 9, 1)

    body = client.get("/margin", params={"campaign_id": client.get("/margin").json()["campaigns"][0]["campaign_id"]}).json()

    assert body["campaigns"][0]["totals"]["margin_pct"] is None and body["totals"]["margin_pct"] is None
    assert body["totals"]["revenue"] == "0.00" and body["totals"]["margin"] == "-520.00"
