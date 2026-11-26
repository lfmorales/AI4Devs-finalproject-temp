"""POST and GET /billing/flights/{id}/adjustments (finance/billing-adjustment).

The worked flight: a committed line of 1,000,000 impressions at 5.00 € that delivered 700,000 in August 2026 at a media
cost of 1,200.00 €, a flat 25 % rebate and a platform rate of 1.00 €. By the rule it bills 3,500.00 € and its margin is
725.00 €; adjusted to its contracted volume it bills 5,000.00 €, its rebate is 1,250.00 € and its margin 1,850.00 €.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.campaign import CampaignLinePeriodRecord, CampaignLineRecord
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord
from app.infrastructure.persistence.models.identity import UserRecord
from app.infrastructure.persistence.models.margin import AppliedRateRecord, FlightBillingAdjustmentRecord
from app.infrastructure.persistence.repositories import sqlalchemy_billing_adjustment_repository as repository
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import (
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    replace_flights,
)
from tests.fixtures.margin_data import add_schedule, group_of, make_month_closable, set_volume

JULY = (date(2026, 7, 1), date(2026, 7, 31))
AUGUST = (date(2026, 8, 1), date(2026, 8, 31))
PENDING_CLOSE = date(2026, 9, 1)  # D-1 is 31 August: August has ended and is not closed
RUNNING = date(2026, 8, 11)  # D-1 is 10 August: August runs
REASON = "Acuerdo con la agencia: se factura la OC completa"
POST_FIELDS = {"id", "flight_id", "basis", "amount", "reason", "created_by", "created_at", "billing"}
MONEY_WORDS = ("revenue", "cost", "margin", "rebate", "cpm", "price")


def _on(client: TestClient, today: date = PENDING_CLOSE) -> TestClient:
    """Pin D and confirm the data prepared so far: a refused request rolls the service back, and the test session joins
    an outer transaction through a savepoint, so what was only flushed would be lost with it."""
    overrides = client.app.dependency_overrides  # type: ignore[attr-defined]
    overrides[providers.get_today] = lambda: today
    next(overrides[providers.get_db_session]()).commit()
    return client


def _flight_ids(session: Session, line_id: int) -> list[int]:
    return list(session.scalars(
        select(CampaignLinePeriodRecord.id).where(CampaignLinePeriodRecord.campaign_line_id == line_id)
        .order_by(CampaignLinePeriodRecord.flight_start)
    ))


def _worked_flight(session: Session, name: str = "Worked", rate: str = "0.25") -> tuple[int, int]:
    """The worked flight with its schedule; returns its line and its flight."""
    line_id = insert_campaign_line(session, campaign_name=name)
    insert_delivery(session, line_id, date(2026, 8, 10), 700_000, insert_ingestion_batch(session), Decimal("1200.00"))
    add_schedule(session, group_of(session, line_id), ("0", None, rate))
    return line_id, _flight_ids(session, line_id)[0]


def _adjust(client: TestClient, flight_id: int, basis: object = "contracted", amount: object = None,
            reason: object = REASON) -> Any:
    body: dict[str, object] = {"basis": basis, "reason": reason}
    if amount is not None:
        body["amount"] = amount
    return client.post(f"/billing/flights/{flight_id}/adjustments", json=body)


def _flight_of(client: TestClient, line_id: int) -> dict[str, Any]:
    body = client.get("/margin").json()
    (flight,) = [
        f for c in body["campaigns"] for l in c["lines"] if l["campaign_line_id"] == line_id for f in l["flights"]
    ]
    return flight  # type: ignore[no-any-return]


def _rows(session: Session) -> int:
    session.expire_all()
    return int(session.scalar(select(func.count()).select_from(FlightBillingAdjustmentRecord)) or 0)


def _restate_delivery(session: Session, line_id: int, impressions: int) -> None:
    session.execute(update(DailyDeliveryRecord).where(DailyDeliveryRecord.campaign_line_id == line_id).values(
        impressions=impressions))
    session.commit()


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


# ---------------------------------------------------------------- the bases and what they bill


def test_a_flight_adjusted_to_its_contracted_volume_bills_its_whole_contract(client_for_roles: Any, test_db_session: Session) -> None:
    line_id, flight = _worked_flight(test_db_session)
    finance = _on(client_for_roles("finance"))
    by_the_rule = _flight_of(finance, line_id)
    assert (by_the_rule["revenue"], by_the_rule["rebate"], by_the_rule["margin"]) == ("3500.00", "875.00", "725.00")

    response = _adjust(finance, flight, "contracted")

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == POST_FIELDS
    assert (body["flight_id"], body["basis"], body["amount"], body["reason"], body["billing"]) == (
        flight, "contracted", None, REASON, "5000.00",
    )
    adjusted = _flight_of(finance, line_id)
    assert (adjusted["revenue"], adjusted["rebate"], adjusted["media_cost"], adjusted["platform_cost"], adjusted["margin"]) == (
        "5000.00", "1250.00", "1200.00", "700.00", "1850.00",
    )


def test_a_custom_amount_is_fixed_whatever_the_delivery_does(client_for_roles: Any, test_db_session: Session) -> None:
    line_id, flight = _worked_flight(test_db_session)
    finance = _on(client_for_roles("finance"))

    response = _adjust(finance, flight, "custom", "4200.00")

    assert (response.status_code, response.json()["amount"], response.json()["billing"]) == (201, "4200.00", "4200.00")
    figures = _flight_of(finance, line_id)
    assert (figures["revenue"], figures["rebate"], figures["margin"]) == ("4200.00", "1050.00", "1250.00")
    _restate_delivery(test_db_session, line_id, 900_000)
    assert _flight_of(finance, line_id)["revenue"] == "4200.00"


def test_the_delivered_basis_follows_the_delivery_until_the_closing(client_for_roles: Any, test_db_session: Session) -> None:
    line_id, flight = _worked_flight(test_db_session)
    finance = _on(client_for_roles("finance"))
    _adjust(finance, flight, "delivered")
    assert _flight_of(finance, line_id)["revenue"] == "3500.00"

    _restate_delivery(test_db_session, line_id, 720_000)

    assert _flight_of(finance, line_id)["revenue"] == "3600.00"


def test_the_delivered_basis_bills_an_over_delivery(client_for_roles: Any, test_db_session: Session) -> None:
    line_id, flight = _worked_flight(test_db_session)
    finance = _on(client_for_roles("finance"))
    _restate_delivery(test_db_session, line_id, 1_100_000)
    assert _flight_of(finance, line_id)["revenue"] == "5000.00"

    response = _adjust(finance, flight, "delivered")

    assert response.json()["billing"] == "5500.00"
    assert _flight_of(finance, line_id)["revenue"] == "5500.00"


def test_a_custom_amount_of_zero_bills_nothing(client_for_roles: Any, test_db_session: Session) -> None:
    line_id, flight = _worked_flight(test_db_session)
    finance = _on(client_for_roles("finance"))

    response = _adjust(finance, flight, "custom", "0.00")

    assert (response.status_code, response.json()["billing"]) == (201, "0.00")
    figures = _flight_of(finance, line_id)
    assert (figures["revenue"], figures["rebate"]) == ("0.00", "0.00")


@pytest.mark.parametrize(("billable", "billing"), [(False, "2500.00"), (True, "3000.00")])
def test_the_contracted_basis_bills_the_cap_with_a_billable_carry_over(
    client_for_roles: Any, test_db_session: Session, billable: bool, billing: str
) -> None:
    line_id = insert_campaign_line(test_db_session, campaign_name="Cap")
    set_volume(test_db_session, line_id, 500_000)
    insert_delivery(test_db_session, line_id, date(2026, 8, 10), 450_000, insert_ingestion_batch(test_db_session))
    flight = _flight_ids(test_db_session, line_id)[0]
    finance = client_for_roles("finance")
    author = test_db_session.scalars(select(UserRecord.id)).first()
    test_db_session.execute(update(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.id == flight).values(
        carryover=100_000, carryover_reason="Recuperar", carryover_set_by=author, carryover_set_at=datetime(2026, 8, 2),
        carryover_billable=billable, carryover_billable_set_by=author if billable else None,
        carryover_billable_set_at=datetime(2026, 8, 3) if billable else None,
    ))

    response = _adjust(_on(finance), flight, "contracted")

    assert response.json()["billing"] == billing


def test_the_minimum_basis_returns_the_flight_to_the_rule(client_for_roles: Any, test_db_session: Session) -> None:
    line_id, flight = _worked_flight(test_db_session)
    finance = _on(client_for_roles("finance"))
    _adjust(finance, flight, "contracted")

    response = _adjust(finance, flight, "minimum", reason="Se factura lo entregado")

    assert (response.status_code, response.json()["billing"]) == (201, "3500.00")
    assert _flight_of(finance, line_id)["revenue"] == "3500.00"


# ---------------------------------------------------------------- the adjusted billing moves the rebate and the counter


def test_an_adjusted_billing_moves_the_rebate_and_the_counter_with_figures(
    client_for_roles: Any, test_db_session: Session
) -> None:
    # Brackets: 10 % up to 5,000 € and 20 % above. July and August each deliver their million and bill 5,000.00 €.
    line_id = insert_campaign_line(test_db_session, campaign_name="Counter", start_date=JULY[0], end_date=AUGUST[1])
    replace_flights(test_db_session, line_id, [JULY, AUGUST])
    set_volume(test_db_session, line_id, 1_000_000)
    batch = insert_ingestion_batch(test_db_session)
    insert_delivery(test_db_session, line_id, date(2026, 7, 10), 1_000_000, batch)
    insert_delivery(test_db_session, line_id, date(2026, 8, 10), 1_000_000, batch)
    add_schedule(test_db_session, group_of(test_db_session, line_id), ("0", "5000", "0.10"), ("5000", None, "0.20"))
    july, august = _flight_ids(test_db_session, line_id)
    finance = _on(client_for_roles("finance"))

    def rebates() -> tuple[str, str]:
        body = finance.get("/margin").json()
        flights = {f["flight_id"]: f for c in body["campaigns"] for l in c["lines"] for f in l["flights"]}
        return flights[july]["rebate"], flights[august]["rebate"]

    # Without an adjustment: July 5,000 at 10 % is 500; August starts at 5,000, all at 20 %, is 1,000.
    assert rebates() == ("500.00", "1000.00")

    _adjust(finance, july, "custom", "3000.00")

    # July bills 3,000: 300 of rebate. August starts at 3,000: 2,000 at 10 % and 3,000 at 20 % is 800.
    assert rebates() == ("300.00", "800.00")
    for month in (7, 8):
        make_month_closable(test_db_session, 2026, month, None, PENDING_CLOSE)
        assert finance.post("/margin/closings", json={"year": 2026, "month": month}).status_code == 200
    test_db_session.expire_all()
    rows = {
        row.campaign_line_period_id: row
        for row in test_db_session.scalars(select(AppliedRateRecord).order_by(AppliedRateRecord.campaign_line_period_id))
    }
    assert (rows[july].position_before, rows[july].position_after, rows[july].rebate_amount) == (
        Decimal(0), Decimal("3000.00"), Decimal("300.00"),
    )
    assert (rows[august].position_before, rows[august].position_after, rows[august].rebate_amount) == (
        Decimal("3000.00"), Decimal("8000.00"), Decimal("800.00"),
    )


# ---------------------------------------------------------------- what is refused


@pytest.mark.parametrize("reason", ["", "   "], ids=["empty", "spaces"])
def test_the_reason_is_mandatory(client_for_roles: Any, test_db_session: Session, reason: str) -> None:
    _, flight = _worked_flight(test_db_session)

    response = _adjust(_on(client_for_roles("finance")), flight, reason=reason)

    assert (response.status_code, response.json()["code"]) == (422, "invalid_adjustment")
    assert set(response.json()) == {"code", "message"}
    assert _rows(test_db_session) == 0


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"basis": "custom", "reason": REASON}, "invalid_adjustment"),
        ({"basis": "contracted", "amount": "100.00", "reason": REASON}, "invalid_adjustment"),
        ({"basis": "delivered", "amount": "100.00", "reason": REASON}, "invalid_adjustment"),
        ({"basis": "custom", "amount": "-1.00", "reason": REASON}, "invalid_adjustment"),
        ({"basis": "custom", "amount": "1.005", "reason": REASON}, "invalid_adjustment"),
        ({"basis": "contracted"}, "validation_error"),
        ({"basis": "reported", "reason": REASON}, "validation_error"),
        ({"basis": "other", "reason": REASON}, "validation_error"),
        ({"reason": REASON}, "validation_error"),
        ({"basis": "custom", "amount": 4200.5, "reason": REASON}, "validation_error"),
        ({"basis": "custom", "amount": "abc", "reason": REASON}, "validation_error"),
    ],
    ids=["custom-no-amount", "contracted-amount", "delivered-amount", "negative", "three-decimals", "no-reason",
         "reported", "unknown", "no-basis", "json-number", "text"],
)
def test_an_invalid_adjustment_is_a_422_with_only_code_and_message(
    client_for_roles: Any, test_db_session: Session, body: dict[str, object], code: str
) -> None:
    _, flight = _worked_flight(test_db_session)

    response = _on(client_for_roles("finance")).post(f"/billing/flights/{flight}/adjustments", json=body)

    assert (response.status_code, response.json()["code"]) == (422, code)
    assert set(response.json()) == {"code", "message"}
    assert _rows(test_db_session) == 0


def test_a_target_flight_is_never_adjusted(client_for_roles: Any, test_db_session: Session) -> None:
    line_id, flight = _worked_flight(test_db_session)
    test_db_session.execute(
        update(CampaignLineRecord).where(CampaignLineRecord.id == line_id).values(volume_commitment="target")
    )

    response = _adjust(_on(client_for_roles("finance")), flight)

    assert (response.status_code, response.json()["code"]) == (409, "target_line_not_adjustable")
    assert set(response.json()) == {"code", "message"}
    assert _rows(test_db_session) == 0


def test_a_running_flight_is_not_adjusted(client_for_roles: Any, test_db_session: Session) -> None:
    _, flight = _worked_flight(test_db_session)

    response = _adjust(_on(client_for_roles("finance"), RUNNING), flight)

    assert (response.status_code, response.json()["code"]) == (409, "flight_not_ended")
    assert _rows(test_db_session) == 0


def test_a_flight_ending_on_the_day_counted_has_ended(client_for_roles: Any, test_db_session: Session) -> None:
    _, flight = _worked_flight(test_db_session)

    assert _adjust(_on(client_for_roles("finance"), date(2026, 9, 1)), flight).status_code == 201


def test_a_frozen_flight_is_not_adjusted(client_for_roles: Any, test_db_session: Session) -> None:
    _, flight = _worked_flight(test_db_session)
    make_month_closable(test_db_session, 2026, 8, None, PENDING_CLOSE)
    finance = _on(client_for_roles("finance"))
    assert finance.post("/margin/closings", json={"year": 2026, "month": 8}).status_code == 200

    response = _adjust(finance, flight)

    assert (response.status_code, response.json()["code"]) == (409, "flight_closed")
    assert _rows(test_db_session) == 0


def test_an_unknown_flight_is_not_found(client_for_roles: Any, test_db_session: Session) -> None:
    finance = _on(client_for_roles("finance"))

    post = _adjust(finance, 999_999)
    history = finance.get("/billing/flights/999999/adjustments")

    assert (post.status_code, post.json()["code"]) == (404, "flight_not_found")
    assert (history.status_code, history.json()["code"]) == (404, "flight_not_found")
    assert set(post.json()) == {"code", "message"}


# ---------------------------------------------------------------- history: the latest is in force


def test_the_latest_adjustment_wins_and_the_history_lists_both_latest_first(
    client_for_roles: Any, test_db_session: Session
) -> None:
    line_id, flight = _worked_flight(test_db_session)
    finance = _on(client_for_roles("operations"))
    _adjust(finance, flight, "contracted", reason="Primero")
    _adjust(finance, flight, "custom", "4200.00", reason="Después")

    history = finance.get(f"/billing/flights/{flight}/adjustments")

    assert history.status_code == 200
    items = history.json()["adjustments"]
    assert [(i["basis"], i["amount"], i["reason"], i["in_force"]) for i in items] == [
        ("custom", "4200.00", "Después", True), ("contracted", None, "Primero", False),
    ]
    assert all({"id", "created_by", "created_at"} <= set(i) for i in items)
    assert _flight_of(finance, line_id)["revenue"] == "4200.00"


def test_returning_to_the_minimum_keeps_the_history(client_for_roles: Any, test_db_session: Session) -> None:
    _, flight = _worked_flight(test_db_session)
    finance = _on(client_for_roles("finance"))
    _adjust(finance, flight, "contracted")
    _adjust(finance, flight, "minimum", reason="Vuelta a la regla")

    items = finance.get(f"/billing/flights/{flight}/adjustments").json()["adjustments"]

    assert [(i["basis"], i["in_force"]) for i in items] == [("minimum", True), ("contracted", False)]


def test_a_flight_without_adjustments_has_an_empty_history(client_for_roles: Any, test_db_session: Session) -> None:
    _, flight = _worked_flight(test_db_session)

    assert _on(client_for_roles("finance")).get(f"/billing/flights/{flight}/adjustments").json() == {"adjustments": []}


def test_the_author_and_the_moment_are_stored(client_for_roles: Any, test_db_session: Session) -> None:
    _, flight = _worked_flight(test_db_session)
    client = _on(client_for_roles("operations"))
    author = test_db_session.scalars(select(UserRecord.id).where(UserRecord.email == "roles_operations@example.com")).one()

    body = _adjust(client, flight, "custom", "4200.00").json()

    test_db_session.expire_all()
    (stored,) = test_db_session.scalars(select(FlightBillingAdjustmentRecord)).all()
    assert (stored.created_by, stored.basis, stored.amount, stored.reason) == (author, "custom", Decimal("4200.00"), REASON)
    assert body["created_by"] == author and body["created_at"] == stored.created_at.isoformat()


def test_the_amount_leaves_as_a_decimal_string(client_for_roles: Any, test_db_session: Session) -> None:
    _, flight = _worked_flight(test_db_session)
    finance = _on(client_for_roles("finance"))

    body = _adjust(finance, flight, "custom", "4200.5").json()
    history = finance.get(f"/billing/flights/{flight}/adjustments").json()["adjustments"][0]

    assert (body["amount"], body["billing"], history["amount"]) == ("4200.50", "4200.50", "4200.50")


# ---------------------------------------------------------------- roles


@pytest.mark.parametrize("role", ["trading", "business"])
def test_trading_and_business_cannot_adjust_or_read_the_adjustments(
    client_for_roles: Any, test_db_session: Session, role: str
) -> None:
    _, flight = _worked_flight(test_db_session)
    _adjust(_on(client_for_roles("finance")), flight, reason="Un motivo que no debe salir")
    client = _on(client_for_roles(role))

    post = _adjust(client, flight)
    history = client.get(f"/billing/flights/{flight}/adjustments")

    for response in (post, history):
        assert response.status_code == 403
        assert set(response.json()) == {"code", "message"}
        assert "motivo" not in response.text.lower()
        assert not any(word in response.text.lower() for word in MONEY_WORDS)
    assert _rows(test_db_session) == 1


@pytest.mark.parametrize("role", ["trading", "business"])
def test_the_reason_of_an_adjustment_reaches_no_other_response_of_trading_or_business(
    client_for_roles: Any, test_db_session: Session, role: str
) -> None:
    line_id, flight = _worked_flight(test_db_session)
    _adjust(_on(client_for_roles("finance")), flight, "custom", "4200.00", reason="Motivo confidencial del ajuste")
    client = _on(client_for_roles(role))

    status = client.get("/campaign-status")

    assert status.status_code == 200
    assert "confidencial" not in status.text and "4200" not in status.text
    assert not [name for name in _keys(status.json()) if "adjust" in name.lower() or "reason" in name.lower()]
    assert line_id


def test_the_reason_of_an_adjustment_is_not_in_the_response_to_trading_when_it_writes_a_carry_over(
    client_for_roles: Any, test_db_session: Session
) -> None:
    line_id, flight = _worked_flight(test_db_session)
    _adjust(_on(client_for_roles("finance")), flight, reason="Motivo confidencial del ajuste")
    trading = _on(client_for_roles("trading"))

    response = trading.put(f"/flights/{flight}/carryover", json={"volume": 1, "reason": "x"})

    assert "confidencial" not in response.text and not _keys(response.json()) & {"adjustment", "billing", "basis"}
    assert line_id


@pytest.mark.parametrize("role", ["finance", "operations"])
def test_finance_and_operations_may_adjust(client_for_roles: Any, test_db_session: Session, role: str) -> None:
    _, flight = _worked_flight(test_db_session)

    assert _adjust(_on(client_for_roles(role)), flight).status_code == 201


def test_a_request_without_a_token_is_unauthenticated(client: TestClient) -> None:
    assert _adjust(client, 1).status_code == 401
    assert client.get("/billing/flights/1/adjustments").status_code == 401


def test_the_routes_answer_for_real_and_not_501(client_for_roles: Any, test_db_session: Session) -> None:
    _, flight = _worked_flight(test_db_session)
    finance = _on(client_for_roles("finance"))

    assert _adjust(finance, flight).status_code != 501
    assert finance.get(f"/billing/flights/{flight}/adjustments").status_code != 501


# ---------------------------------------------------------------- the month lock


def test_the_adjustment_takes_the_lock_of_the_month_before_it_writes(
    client_for_roles: Any, test_db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, flight = _worked_flight(test_db_session)
    finance = _on(client_for_roles("finance"))
    calls: list[tuple[str, tuple[int, ...]]] = []
    transaction = repository.SqlAlchemyBillingAdjustmentTransaction
    lock, add = transaction.lock_month, transaction.add_adjustment

    def spy_lock(self: Any, year: int, month: int) -> None:
        calls.append(("lock", (year, month)))
        lock(self, year, month)

    def spy_add(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(("add", ()))
        return add(self, *args, **kwargs)

    monkeypatch.setattr(transaction, "lock_month", spy_lock)
    monkeypatch.setattr(transaction, "add_adjustment", spy_add)

    assert _adjust(finance, flight).status_code == 201

    assert calls == [("lock", (2026, 8)), ("add", ())]


def test_a_refused_adjustment_leaves_the_flight_as_it_was(client_for_roles: Any, test_db_session: Session) -> None:
    line_id, flight = _worked_flight(test_db_session)
    finance = _on(client_for_roles("finance"))
    before = _flight_of(finance, line_id)

    assert _adjust(finance, flight, "custom", "-1.00").status_code == 422

    assert _flight_of(finance, line_id) == before
