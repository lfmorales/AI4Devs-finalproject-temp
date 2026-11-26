"""GET /billing: the billing of a month per campaign, line and flight (finance/billing-report).

The worked month is November 2026, read on 2 December (D-1 is 1 December, so November has ended). The line of the
campaign «Carry» contracted 500,000 in October and 500,000 in November; October delivered 400,000, so 100,000 are
carried to November, made billable, and November delivered 580,000 under a cap of 600,000. The line of «Custom»
contracted 1,000,000 in November, delivered 700,000 and is adjusted to a custom billing of 4,200.00 €.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.infrastructure.persistence.base import Base
from app.infrastructure.persistence.models.campaign import CampaignLinePeriodRecord, CampaignLineRecord
from app.infrastructure.persistence.models.identity import UserRecord
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import (
    campaign_id_of,
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    replace_flights,
)
from tests.fixtures.margin_data import load_months_last_day, make_month_closable, set_volume

OCTOBER = (date(2026, 10, 1), date(2026, 10, 31))
NOVEMBER = (date(2026, 11, 1), date(2026, 11, 30))
AFTER_NOVEMBER = date(2026, 12, 2)  # D-1 is 1 December
REASON = "Acuerdo con la agencia"


def _on(client: TestClient, today: date = AFTER_NOVEMBER) -> TestClient:
    client.app.dependency_overrides[providers.get_today] = lambda: today
    return client


def _user(session: Session, role: str) -> int:
    return int(session.scalars(select(UserRecord.id).where(UserRecord.email == f"roles_{role}@example.com")).one())


def _flight_id(session: Session, line_id: int, month: int) -> int:
    return int(session.scalars(
        select(CampaignLinePeriodRecord.id).where(
            CampaignLinePeriodRecord.campaign_line_id == line_id,
            func.extract("month", CampaignLinePeriodRecord.flight_start) == month,
        )
    ).one())


def _deliver(session: Session, line_id: int, day: date, impressions: int) -> None:
    insert_delivery(session, line_id, day, impressions, insert_ingestion_batch(session), Decimal("100.00"))


def _carry_line(session: Session) -> tuple[int, int, int]:
    """«Carry»: October 400,000 of 500,000, November 580,000 of 500,000. Returns the line and both flights."""
    line_id = insert_campaign_line(session, "Carry", OCTOBER[0], NOVEMBER[1])
    replace_flights(session, line_id, [OCTOBER, NOVEMBER])
    set_volume(session, line_id, 500_000)
    _deliver(session, line_id, date(2026, 10, 10), 400_000)
    _deliver(session, line_id, date(2026, 11, 10), 580_000)
    return line_id, _flight_id(session, line_id, 10), _flight_id(session, line_id, 11)


def _custom_line(session: Session) -> tuple[int, int]:
    """«Custom»: one November flight that delivered 700,000 of its 1,000,000."""
    line_id = insert_campaign_line(session, "Custom", *NOVEMBER)
    replace_flights(session, line_id, [NOVEMBER])
    _deliver(session, line_id, date(2026, 11, 10), 700_000)
    return line_id, _flight_id(session, line_id, 11)


def _november(session: Session, operations: TestClient, finance: TestClient) -> dict[str, int]:
    _, october, november = _carry_line(session)
    _, custom = _custom_line(session)
    carried = operations.put(f"/flights/{november}/carryover", json={"volume": 100_000, "reason": "Falta de octubre"})
    assert carried.status_code == 200, carried.text
    flagged = finance.put(f"/billing/flights/{november}/carryover/billable", json={"billable": True})
    assert flagged.status_code == 200, flagged.text
    adjusted = finance.post(
        f"/billing/flights/{custom}/adjustments", json={"basis": "custom", "amount": "4200.00", "reason": REASON},
    )
    assert adjusted.status_code == 201, adjusted.text
    return {"october": october, "november": november, "custom": custom}


def _read(client: TestClient, **params: object) -> dict[str, Any]:
    response = client.get("/billing", params={"year": 2026, "month": 11, **params})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _flights(body: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {f["flight_id"]: f for c in body["campaigns"] for line in c["lines"] for f in line["flights"]}


def _campaign(body: dict[str, Any], name: str) -> dict[str, Any]:
    (campaign,) = [c for c in body["campaigns"] if c["name"] == name]
    found: dict[str, Any] = campaign
    return found


@pytest.fixture
def clients(client_for_roles: Any) -> tuple[TestClient, TestClient]:
    return _on(client_for_roles("operations")), _on(client_for_roles("finance"))


# ---------------------------------------------------------------- the month, its flights and their billing


def test_the_november_month_with_a_billable_carry_over_and_a_custom_adjustment(
    clients: tuple[TestClient, TestClient], test_db_session: Session
) -> None:
    operations, finance = clients
    ids = _november(test_db_session, operations, finance)

    body = _read(finance)

    assert (body["year"], body["month"], body["as_of"]) == (2026, 11, "2026-12-01")
    flights = _flights(body)
    assert set(flights) == {ids["november"], ids["custom"]}  # October's flight belongs to October
    carried = flights[ids["november"]]
    assert carried == {
        "flight_id": ids["november"], "flight_start": "2026-11-01", "flight_end": "2026-11-30", "state": "pending_close",
        "delivery_metric": "impressions", "contracted_impressions": 500_000, "carryover": 100_000,
        "carryover_billable": True, "delivery_target": 600_000, "delivered": "580000.0000", "billable": "580000.0000",
        "billing": "2900.00", "billing_basis": "minimum", "sale_cpm": "5.00", "adjustment": None,
    }
    custom = flights[ids["custom"]]
    assert (custom["billing"], custom["billing_basis"], custom["billable"]) == ("4200.00", "custom", None)
    adjustment = custom["adjustment"]
    assert (adjustment["basis"], adjustment["amount"], adjustment["reason"], adjustment["created_by"]) == (
        "custom", "4200.00", REASON, _user(test_db_session, "finance"),
    )
    assert datetime.fromisoformat(adjustment["created_at"])


def test_each_campaign_carries_its_name_agency_and_advertiser_and_each_line_its_number(
    clients: tuple[TestClient, TestClient], test_db_session: Session
) -> None:
    operations, finance = clients
    _november(test_db_session, operations, finance)

    campaign = _campaign(_read(finance), "Carry")

    assert (campaign["agency"], campaign["advertiser"]) == ("Carry agency", "Carry advertiser")
    assert campaign["campaign_id"] == campaign_id_of(test_db_session, campaign["lines"][0]["campaign_line_id"])
    assert [line["line_number"] for line in campaign["lines"]] == [1]


def test_the_billing_read_and_the_margin_read_agree_on_every_flight(
    clients: tuple[TestClient, TestClient], test_db_session: Session
) -> None:
    operations, finance = clients
    _november(test_db_session, operations, finance)

    billing = _flights(_read(finance))
    margin = {
        f["flight_id"]: f for c in finance.get("/margin", params={"year": 2026, "month": 11}).json()["campaigns"]
        for line in c["lines"] for f in line["flights"]
    }

    assert set(billing) == set(margin)
    for flight_id, flight in billing.items():
        assert (flight["billing"], flight["billable"], flight["billing_basis"]) == (
            margin[flight_id]["revenue"], margin[flight_id]["billable"], margin[flight_id]["billing_basis"],
        )
        assert (flight["delivered"], flight["contracted_impressions"]) == (
            margin[flight_id]["delivered"], margin[flight_id]["contracted_impressions"],
        )


def test_a_closed_flight_is_read_from_its_snapshot(clients: tuple[TestClient, TestClient], test_db_session: Session) -> None:
    operations, finance = clients
    line_id, october, _ = _carry_line(test_db_session)
    make_month_closable(test_db_session, 2026, 10, None, AFTER_NOVEMBER)
    assert finance.post("/margin/closings", json={"year": 2026, "month": 10}).status_code == 200
    # After the closing the line's price and October's contracted volume change: the closed flight keeps its own.
    test_db_session.execute(update(CampaignLineRecord).where(CampaignLineRecord.id == line_id).values(sale_cpm=Decimal("9.00")))
    test_db_session.execute(
        update(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.id == october).values(contracted_impressions=900_000)
    )
    test_db_session.flush()

    (flight,) = _flights(_read(finance, month=10)).values()

    assert (flight["state"], flight["sale_cpm"], flight["contracted_impressions"]) == ("closed", "5.00", 500_000)
    assert (flight["billing"], flight["billable"], flight["billing_basis"]) == ("2000.00", "400000.0000", "minimum")
    assert (flight["carryover"], flight["carryover_billable"], flight["delivery_target"]) == (0, False, 500_000)


def test_a_flight_that_has_not_started_carries_no_billing(
    clients: tuple[TestClient, TestClient], test_db_session: Session
) -> None:
    _, finance = clients
    line_id, _, november = _carry_line(test_db_session)

    flights = _flights(_read(_on(finance, date(2026, 10, 20))))  # D-1 is 19 October: November has not started

    assert line_id
    assert {key: flights[november][key] for key in ("state", "delivered", "billable", "billing", "billing_basis")} == {
        "state": "not_started", "delivered": None, "billable": None, "billing": None, "billing_basis": None,
    }
    assert (flights[november]["contracted_impressions"], flights[november]["delivery_target"]) == (500_000, 500_000)


def test_a_running_flight_carries_its_billing_to_date(clients: tuple[TestClient, TestClient], test_db_session: Session) -> None:
    _, finance = clients
    _, _, november = _carry_line(test_db_session)

    flights = _flights(_read(_on(finance, date(2026, 11, 20))))

    assert (flights[november]["state"], flights[november]["billing"], flights[november]["billable"]) == (
        "running", "2500.00", "500000.0000",
    )


# ---------------------------------------------------------------- the review state of each campaign


def test_each_campaign_carries_its_review_state_and_the_reviewed_one_its_author_and_moment(
    clients: tuple[TestClient, TestClient], test_db_session: Session
) -> None:
    _, finance = clients
    reviewed, _ = _custom_line(test_db_session)
    pending = insert_campaign_line(test_db_session, "Pending", *NOVEMBER)
    replace_flights(test_db_session, pending, [NOVEMBER])
    running = insert_campaign_line(test_db_session, "Running", date(2026, 11, 1), date(2026, 12, 31))
    replace_flights(test_db_session, running, [(date(2026, 11, 1), date(2026, 11, 30))])
    for line_id in (reviewed, pending):  # both end on the 20th; «Running» ends on the 30th
        test_db_session.execute(update(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.campaign_line_id == line_id)
                                .values(flight_end=date(2026, 11, 20)))
    load_months_last_day(test_db_session, 2026, 11)
    review = finance.post("/billing/reviews", json={"campaign_id": campaign_id_of(test_db_session, reviewed), "year": 2026,
                                                    "month": 11})
    assert review.status_code == 201, review.text

    body = _read(_on(finance, date(2026, 11, 30)))  # D-1 is 29 November: «Running» ends on the 30th

    custom, waiting, in_progress = (_campaign(body, name) for name in ("Custom", "Pending", "Running"))
    assert (custom["review_state"], custom["review_set_by"], custom["review_set_at"]) == (
        "reviewed", _user(test_db_session, "finance"), review.json()["set_at"],
    )
    assert (waiting["review_state"], waiting["review_set_by"], waiting["review_set_at"]) == ("pending_review", None, None)
    assert in_progress["review_state"] == "in_progress"


def test_a_closed_campaign_reads_as_closed(clients: tuple[TestClient, TestClient], test_db_session: Session) -> None:
    _, finance = clients
    _custom_line(test_db_session)
    make_month_closable(test_db_session, 2026, 11, None, AFTER_NOVEMBER)
    assert finance.post("/margin/closings", json={"year": 2026, "month": 11}).status_code == 200

    assert _campaign(_read(finance), "Custom")["review_state"] == "closed"


def test_the_campaign_filter_keeps_one_campaign(clients: tuple[TestClient, TestClient], test_db_session: Session) -> None:
    operations, finance = clients
    _november(test_db_session, operations, finance)
    custom = _campaign(_read(finance), "Custom")["campaign_id"]

    body = _read(finance, campaign_id=custom)

    assert [c["name"] for c in body["campaigns"]] == ["Custom"]


# ---------------------------------------------------------------- nothing is written; errors; roles


def _row_counts(session: Session) -> dict[str, int]:
    return {table.name: int(session.scalar(select(func.count()).select_from(table)) or 0) for table in Base.metadata.sorted_tables}


def test_reading_writes_nothing(clients: tuple[TestClient, TestClient], test_db_session: Session) -> None:
    operations, finance = clients
    _november(test_db_session, operations, finance)
    before = _row_counts(test_db_session)

    _read(finance)
    _read(operations)

    assert _row_counts(test_db_session) == before


def test_an_unknown_campaign_is_not_found(clients: tuple[TestClient, TestClient]) -> None:
    response = clients[1].get("/billing", params={"year": 2026, "month": 11, "campaign_id": 999_999})

    assert (response.status_code, response.json()) == (
        404, {"code": "campaign_not_found", "message": response.json()["message"]},
    )


@pytest.mark.parametrize("params", [{"year": 2026, "month": 13}, {"year": 2026}, {"month": 11}, {"year": "soon", "month": 11}])
def test_a_missing_or_invalid_month_is_a_validation_error_with_code_and_message_only(
    clients: tuple[TestClient, TestClient], params: dict[str, object]
) -> None:
    response = clients[1].get("/billing", params=params)

    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"} and response.json()["code"] == "validation_error"


@pytest.mark.parametrize("role", ["trading", "business"])
def test_trading_and_business_are_forbidden(client_for_roles: Any, role: str) -> None:
    response = _on(client_for_roles(role)).get("/billing", params={"year": 2026, "month": 11})

    assert response.status_code == 403
    assert set(response.json()) == {"code", "message"}


def test_a_request_without_a_token_is_unauthenticated(client: TestClient) -> None:
    assert client.get("/billing", params={"year": 2026, "month": 11}).status_code == 401
