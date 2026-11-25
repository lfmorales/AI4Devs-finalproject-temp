"""GET /margin for target flights: the gross, the commitment and the two flags at every level (finance/margin-reporting).

August 2026, read on 1 September (as_of 31 August), so every August flight is pending close. The campaign has a flat
10 % schedule and the system platform rate of 1.00 € per thousand.
"""

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.campaign import CampaignLineRecord
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import (
    add_line_to_campaign,
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    replace_flights,
)
from tests.fixtures.margin_data import add_schedule, group_of

SEPTEMBER_FIRST = date(2026, 9, 1)


def _finance(client_for_roles: Callable[..., TestClient]) -> TestClient:
    client = client_for_roles("finance")
    client.app.dependency_overrides[providers.get_today] = lambda: SEPTEMBER_FIRST
    return client


def _margin(client: TestClient) -> dict[str, Any]:
    response = client.get("/margin")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _make_target(session: Session, line_id: int) -> None:
    session.execute(update(CampaignLineRecord).where(CampaignLineRecord.id == line_id).values(volume_commitment="target"))
    session.flush()


def _worked_example(session: Session) -> tuple[int, int]:
    """Line 1 committed (1,000,000 at 5.00 €, no delivery); line 2 the worked example: a target of 1,000,000 at 5.00 €,
    1,100,000 served, 4,400.00 € reported and 5,500.00 € of buyer's spend."""
    committed = insert_campaign_line(session, "Worked example")
    target = add_line_to_campaign(session, committed, 2)
    _make_target(session, target)
    batch = insert_ingestion_batch(session)
    insert_delivery(
        session, target, date(2026, 8, 10), 600_000, batch, buyer_spend=Decimal("3000.00"),
        reported_revenue=Decimal("2400.00"),
    )
    insert_delivery(
        session, target, date(2026, 8, 31), 500_000, batch, buyer_spend=Decimal("2500.00"),
        reported_revenue=Decimal("2000.00"),
    )
    add_schedule(session, group_of(session, committed), ("0", None, "0.10"))
    return committed, target


def _line(body: dict[str, Any], line_id: int) -> dict[str, Any]:
    (line,) = [l for c in body["campaigns"] for l in c["lines"] if l["campaign_line_id"] == line_id]
    found: dict[str, Any] = line
    return found


def test_the_worked_example_reports_its_revenue_its_sale_its_gross_and_its_margin(
    client_for_roles: Callable[..., TestClient], test_db_session: Session
) -> None:
    _, target = _worked_example(test_db_session)

    (flight,) = _line(_margin(_finance(client_for_roles)), target)["flights"]

    assert flight["volume_commitment"] == "target"
    assert (flight["revenue"], flight["contracted_revenue"], flight["gross_revenue"]) == ("4400.00", "5000.00", "5500.00")
    assert (flight["media_cost"], flight["rebate"], flight["platform_cost"]) == ("0.00", "550.00", "1100.00")
    assert (flight["margin"], flight["margin_pct"]) == ("2750.00", "62.50")
    assert (flight["gross_differs_from_buyer_spend"], flight["data_cost_reported"]) == (False, False)


def test_a_committed_flight_has_no_gross_and_no_flag_raised_by_it(
    client_for_roles: Callable[..., TestClient], test_db_session: Session
) -> None:
    committed, _ = _worked_example(test_db_session)

    (flight,) = _line(_margin(_finance(client_for_roles)), committed)["flights"]

    assert flight["volume_commitment"] == "committed"
    assert flight["gross_revenue"] is None
    assert flight["gross_differs_from_buyer_spend"] is False
    assert flight["revenue"] == "5000.00"


def test_a_line_carries_its_commitment_and_a_campaign_of_both_carries_none_and_the_gross_of_its_target_line(
    client_for_roles: Callable[..., TestClient], test_db_session: Session
) -> None:
    committed, target = _worked_example(test_db_session)

    body = _margin(_finance(client_for_roles))
    (campaign,) = body["campaigns"]

    assert (_line(body, target)["totals"]["volume_commitment"], _line(body, target)["totals"]["gross_revenue"]) == (
        "target", "5500.00",
    )
    assert (_line(body, committed)["totals"]["volume_commitment"], _line(body, committed)["totals"]["gross_revenue"]) == (
        "committed", None,
    )
    assert (campaign["totals"]["volume_commitment"], campaign["totals"]["gross_revenue"]) == (None, "5500.00")
    assert (body["totals"]["volume_commitment"], body["totals"]["gross_revenue"]) == (None, "5500.00")


def test_the_flags_are_counted_at_the_line_the_campaign_and_the_totals(
    client_for_roles: Callable[..., TestClient], test_db_session: Session
) -> None:
    # One target line, two flights: the first is paid above its gross (3,000.00 € against 4,000.00 €), the second
    # reports an audience data cost of 1.25 €. No amount changes because of either.
    line = insert_campaign_line(test_db_session, "Two flags")
    _make_target(test_db_session, line)
    replace_flights(test_db_session, line, [(date(2026, 8, 1), date(2026, 8, 15)), (date(2026, 8, 16), date(2026, 8, 31))])
    batch = insert_ingestion_batch(test_db_session)
    insert_delivery(
        test_db_session, line, date(2026, 8, 10), 600_000, batch, buyer_spend=Decimal("4000.00"),
        reported_revenue=Decimal("2400.00"),
    )
    insert_delivery(
        test_db_session, line, date(2026, 8, 20), 500_000, batch, buyer_spend=Decimal("2500.00"),
        reported_revenue=Decimal("2000.00"), audience_data_cost=Decimal("1.25"),
    )

    body = _margin(_finance(client_for_roles))
    (campaign,) = body["campaigns"]
    first, second = _line(body, line)["flights"]

    assert (first["gross_differs_from_buyer_spend"], first["data_cost_reported"]) == (True, False)
    assert (second["gross_differs_from_buyer_spend"], second["data_cost_reported"]) == (False, True)
    for totals in (_line(body, line)["totals"], campaign["totals"], body["totals"]):
        assert (totals["gross_differs_count"], totals["data_cost_count"]) == (1, 1)
    assert _line(body, line)["totals"]["revenue"] == "4400.00"


def test_the_gross_is_a_decimal_string_and_the_counts_are_integers(
    client_for_roles: Callable[..., TestClient], test_db_session: Session
) -> None:
    _worked_example(test_db_session)

    body = _margin(_finance(client_for_roles))

    assert isinstance(body["totals"]["gross_revenue"], str)
    assert type(body["totals"]["gross_differs_count"]) is int and type(body["totals"]["data_cost_count"]) is int
