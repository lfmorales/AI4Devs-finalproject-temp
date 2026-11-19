"""GET /margin over campaigns counted in different metrics: the grand total cannot add their volumes."""

from collections.abc import Callable
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import insert_campaign_line, insert_delivery, insert_ingestion_batch

SEPTEMBER_FIRST = date(2026, 9, 1)  # as_of is 31 August: August is over


def _campaign(session: Session, name: str, metric: str, impressions: int, ots: str = "0") -> None:
    line_id = insert_campaign_line(session, campaign_name=name, delivery_metric=metric)
    insert_delivery(
        session, line_id, date(2026, 8, 10), impressions, insert_ingestion_batch(session), ots=Decimal(ots)
    )


def test_a_dooh_and_a_ctv_campaign_give_a_200_with_a_null_contracted_volume_and_summed_impressions(
    client_for_roles: Callable[..., TestClient], test_db_session: Session
) -> None:
    client = client_for_roles("finance")
    client.app.dependency_overrides[providers.get_today] = lambda: SEPTEMBER_FIRST
    _campaign(test_db_session, "Dooh", "ots", 12_000, "280000.5000")
    _campaign(test_db_session, "Ctv", "impressions", 198_800)

    response = client.get("/margin")

    assert response.status_code == 200, response.text
    totals = response.json()["totals"]
    assert totals["contracted_impressions"] is None
    assert totals["delivered_impressions"] == 210_800


def test_the_totals_of_one_campaign_keep_their_contracted_volume(
    client_for_roles: Callable[..., TestClient], test_db_session: Session
) -> None:
    client = client_for_roles("finance")
    client.app.dependency_overrides[providers.get_today] = lambda: SEPTEMBER_FIRST
    _campaign(test_db_session, "Dooh", "ots", 12_000, "280000.5000")

    body = client.get("/margin").json()

    assert body["totals"]["contracted_impressions"] == 1_000_000
    assert body["campaigns"][0]["totals"]["contracted_impressions"] == 1_000_000
