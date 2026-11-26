"""GET /margin reports a closed flight whose delivery changed after its closing; no figure moves (finance/margin-reporting).

The committed example: November, 1,000,000 contracted at 5.00 €, a flat rebate of 25 %, closed on 1 December with
700,000 impressions and 1,200.00 € of media cost; it bills the 700,000 it delivered, 3,500.00 €, with a rebate of
875.00 € and a margin of 725.00 € (committed-billing-and-review); restated with 1,200,000 impressions and 3,000.00 € of
media cost. The Deal example: a target of 1,000,000 at 5.00 € on Equativ, closed with 1,100,000 served,
4,400.00 € reported and 5,500.00 € spent, a flat rebate of 10 % on its gross, a margin of 2,750.00 €; restated with
1,300,000 served, 5,200.00 € reported and 6,500.00 € spent.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.campaign import CampaignLineRecord
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord, IngestionBatchRecord
from app.infrastructure.persistence.models.masters import DSPRecord
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import (
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    insert_other_dsp,
    replace_flights,
)
from tests.fixtures.margin_data import add_schedule, group_of

NOVEMBER = (date(2026, 11, 1), date(2026, 11, 30))
DECEMBER_FIRST = date(2026, 12, 1)
DECEMBER_FOURTH = date(2026, 12, 4)  # as_of is 3 December
DELIVERY_CHANGE_FIELDS = {
    "delivered_difference", "delivered_impressions_difference", "media_cost_difference",
    "reported_revenue_difference", "buyer_spend_difference", "current_margin", "margin_difference",
}


def _on(client: TestClient, today: date) -> TestClient:
    client.app.dependency_overrides[providers.get_today] = lambda: today
    return client


def _line(session: Session, name: str, window: tuple[date, date] = NOVEMBER) -> int:
    line_id = insert_campaign_line(session, name, *window)
    replace_flights(session, line_id, [window])
    return line_id


class _Month:
    def __init__(self, session: Session, finance: TestClient) -> None:
        self.session = session
        self.finance = finance
        self.committed = _line(session, "Adform committed")
        add_schedule(session, group_of(session, self.committed), ("0", None, "0.25"))
        batch = insert_ingestion_batch(session)
        insert_delivery(session, self.committed, date(2026, 11, 28), 700_000, batch, Decimal("1200.00"))

        equativ = session.scalars(select(DSPRecord.id).where(DSPRecord.name == "Equativ")).first() or insert_other_dsp(
            session, "Equativ"
        )
        self.target = _line(session, "Equativ Deal")
        session.execute(
            update(CampaignLineRecord).where(CampaignLineRecord.id == self.target)
            .values(volume_commitment="target", dsp_id=equativ)
        )
        add_schedule(session, group_of(session, self.target), ("0", None, "0.10"))
        equativ_batch = IngestionBatchRecord(
            dsp_id=equativ, route="api", source_file=None, started_at=datetime(2026, 12, 1, 6, 15),
            finished_at=datetime(2026, 12, 1, 6, 20), status="succeeded", row_count=1,
            window_start=date(2026, 11, 24), window_end=date(2026, 11, 30),
        )
        session.add(equativ_batch)
        session.flush()
        insert_delivery(session, self.target, date(2026, 11, 30), 1_100_000, equativ_batch.id,
                        reported_revenue=Decimal("4400.00"), buyer_spend=Decimal("5500.00"))
        # December: one flight still running and one ended but not closed on 4 December.
        self.running = _line(session, "Running", (date(2026, 12, 1), date(2026, 12, 31)))
        self.pending = _line(session, "Pending close", (date(2026, 12, 1), date(2026, 12, 2)))

    def restate(self) -> None:
        self.session.execute(
            update(DailyDeliveryRecord).where(DailyDeliveryRecord.campaign_line_id == self.committed)
            .values(impressions=1_200_000, media_cost=Decimal("3000.00"))
        )
        self.session.execute(
            update(DailyDeliveryRecord).where(DailyDeliveryRecord.campaign_line_id == self.target)
            .values(impressions=1_300_000, reported_revenue=Decimal("5200.00"), buyer_spend=Decimal("6500.00"))
        )
        self.session.flush()


    def read(self) -> dict[str, Any]:
        response = _on(self.finance, DECEMBER_FOURTH).get("/margin")
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body


@pytest.fixture
def closed_month(client_for_roles: Any, test_db_session: Session) -> _Month:
    month = _Month(test_db_session, client_for_roles("finance"))
    response = _on(month.finance, DECEMBER_FIRST).post("/margin/closings", json={"year": 2026, "month": 11})
    assert response.status_code == 200, response.text
    assert response.json()["closed"] == 2
    return month


def _by_name(body: dict[str, Any], name: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    (campaign,) = [c for c in body["campaigns"] if c["name"] == name]
    (line,) = campaign["lines"]
    (flight,) = line["flights"]
    return campaign, line, flight


def test_the_restated_committed_flight_reports_its_change_and_keeps_its_frozen_figures(
    client_for_roles: Any, closed_month: _Month
) -> None:
    closed_month.restate()

    campaign, line, flight = _by_name(closed_month.read(), "Adform committed")

    assert (flight["state"], flight["revenue"], flight["margin"], flight["media_cost"], flight["platform_cost"]) == (
        "closed", "3500.00", "725.00", "1200.00", "700.00",
    )
    assert flight["delivered_impressions"] == 700_000
    assert flight["delivery_changed"] is True
    assert flight["delivery_change"] == {
        "delivered_difference": "500000.0000", "delivered_impressions_difference": 500_000,
        "media_cost_difference": "1800.00", "reported_revenue_difference": None, "buyer_spend_difference": None,
        # pending-9.4: margin and motive. The check keeps the frozen revenue of a committed flight: 3,500.00 - 3,000.00 - 875.00 -
        # 1,200.00. Task 9.4 compares with the current billing instead (5,000.00, a current margin of -75.00).
        "current_margin": "-1575.00", "margin_difference": "-2300.00",
    }
    for totals in (line["totals"], campaign["totals"]):
        assert (totals["delivery_changed_count"], totals["margin"]) == (1, "725.00")


def test_the_restated_target_flight_reports_its_revenue_and_spend_differences(
    client_for_roles: Any, closed_month: _Month
) -> None:
    closed_month.restate()

    _, _, flight = _by_name(closed_month.read(), "Equativ Deal")

    assert (flight["revenue"], flight["gross_revenue"], flight["rebate"], flight["margin"]) == (
        "4400.00", "5500.00", "550.00", "2750.00",
    )
    assert flight["delivery_changed"] is True
    assert flight["delivery_change"] == {
        "delivered_difference": "200000.0000", "delivered_impressions_difference": 200_000,
        "media_cost_difference": "0.00", "reported_revenue_difference": "800.00", "buyer_spend_difference": "1000.00",
        "current_margin": "3350.00", "margin_difference": "600.00",
    }


def test_the_totals_count_the_changed_flights_and_add_only_the_frozen_margins(
    client_for_roles: Any, closed_month: _Month
) -> None:
    before = closed_month.read()
    closed_month.restate()

    after = closed_month.read()

    assert (before["totals"]["delivery_changed_count"], after["totals"]["delivery_changed_count"]) == (0, 2)
    assert {key: value for key, value in after["totals"].items() if key != "delivery_changed_count"} == {
        key: value for key, value in before["totals"].items() if key != "delivery_changed_count"
    }


def test_a_closed_flight_whose_delivery_did_not_change_reports_zeros(
    client_for_roles: Any, closed_month: _Month
) -> None:
    _, line, flight = _by_name(closed_month.read(), "Adform committed")

    assert flight["delivery_changed"] is False
    assert flight["delivery_change"] == {
        "delivered_difference": "0.0000", "delivered_impressions_difference": 0, "media_cost_difference": "0.00",
        "reported_revenue_difference": None, "buyer_spend_difference": None,
        "current_margin": flight["margin"], "margin_difference": "0.00",
    }
    assert line["totals"]["delivery_changed_count"] == 0


def test_a_running_or_pending_close_flight_carries_no_change(client_for_roles: Any, closed_month: _Month) -> None:
    closed_month.restate()
    body = closed_month.read()

    for name, state in (("Running", "running"), ("Pending close", "pending_close")):
        _, line, flight = _by_name(body, name)
        assert (flight["state"], flight["delivery_changed"], flight["delivery_change"]) == (state, False, None)
        assert line["totals"]["delivery_changed_count"] == 0


def test_every_flight_and_level_carries_the_fields_with_their_types(client_for_roles: Any, closed_month: _Month) -> None:
    closed_month.restate()
    body = closed_month.read()

    assert type(body["totals"]["delivery_changed_count"]) is int
    for campaign in body["campaigns"]:
        assert type(campaign["totals"]["delivery_changed_count"]) is int
        for line in campaign["lines"]:
            assert type(line["totals"]["delivery_changed_count"]) is int
            for flight in line["flights"]:
                assert type(flight["delivery_changed"]) is bool
                change = flight["delivery_change"]
                assert change is None or set(change) == DELIVERY_CHANGE_FIELDS


@pytest.mark.parametrize("role", ["trading", "business"])
def test_a_user_without_operations_or_finance_is_still_forbidden_on_both_routes(
    client_for_roles: Any, closed_month: _Month, role: str
) -> None:
    closed_month.restate()
    client = _on(client_for_roles(role), DECEMBER_FOURTH)

    for response in (client.get("/margin"), client.post("/margin/closings", json={"year": 2026, "month": 11})):
        assert response.status_code == 403
        assert "delivery_change" not in response.text and "closings" not in response.text
