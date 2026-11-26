"""The author of every billing event is named: the user's id and their name, or their email when the name is blank
(finance/billing-report, «The author of every billing event is named»).

The worked month is November 2026 of `test_billing_endpoint.py`, read on 2 December.
"""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.identity import UserRecord
from tests.api.test_billing_endpoint import REASON, _campaign, _carry_line, _custom_line, _on, _read
from tests.fixtures.margin_data import load_months_last_day

CARRYOVER_FIELDS = {
    "flight_id", "delivery_metric", "contracted_impressions", "carryover", "delivery_target", "reason", "set_by",
    "set_by_name", "set_at",
}


def _named(session: Session, role: str, name: str) -> int:
    """The E2E-like user of `client_for_roles(role)`, renamed; returns its id."""
    email = f"roles_{role}@example.com"
    session.execute(update(UserRecord).where(UserRecord.email == email).values(full_name=name))
    session.flush()
    return int(session.scalars(select(UserRecord.id).where(UserRecord.email == email)).one())


def test_a_review_and_its_withdrawal_name_their_author_and_so_does_the_billing_read(
    client_for_roles: Any, test_db_session: Session
) -> None:
    finance = _on(client_for_roles("finance"))
    ana = _named(test_db_session, "finance", "Ana Pérez")
    _, custom = _custom_line(test_db_session)
    load_months_last_day(test_db_session, 2026, 11)
    campaign_id = _campaign(_read(finance), "Custom")["campaign_id"]
    body = {"campaign_id": campaign_id, "year": 2026, "month": 11}

    reviewed = finance.post("/billing/reviews", json=body).json()
    read = _campaign(_read(finance), "Custom")
    withdrawn = finance.post("/billing/reviews/withdrawals", json=body).json()

    assert (reviewed["set_by"], reviewed["set_by_name"]) == (ana, "Ana Pérez")
    assert (read["review_set_by"], read["review_set_by_name"]) == (ana, "Ana Pérez")
    assert (withdrawn["set_by"], withdrawn["set_by_name"]) == (ana, "Ana Pérez")
    assert custom


def test_an_adjustment_names_its_author_in_its_response_its_history_and_the_billing_read(
    client_for_roles: Any, test_db_session: Session
) -> None:
    finance = _on(client_for_roles("finance"))
    ana = _named(test_db_session, "finance", "Ana Pérez")
    _, custom = _custom_line(test_db_session)

    response = finance.post(f"/billing/flights/{custom}/adjustments",
                            json={"basis": "custom", "amount": "4200.00", "reason": REASON}).json()
    (item,) = finance.get(f"/billing/flights/{custom}/adjustments").json()["adjustments"]
    (line,) = _campaign(_read(finance), "Custom")["lines"]
    (flight,) = line["flights"]

    assert (response["created_by"], response["created_by_name"]) == (ana, "Ana Pérez")
    assert (item["created_by"], item["created_by_name"]) == (ana, "Ana Pérez")
    assert (flight["adjustment"]["created_by"], flight["adjustment"]["created_by_name"]) == (ana, "Ana Pérez")


def test_the_billable_flag_names_its_author_by_the_email_when_the_name_is_blank(
    client_for_roles: Any, test_db_session: Session
) -> None:
    operations = _on(client_for_roles("operations"))
    finance = _on(client_for_roles("finance"))
    _named(test_db_session, "finance", "   ")
    _, _, november = _carry_line(test_db_session)
    assert operations.put(f"/flights/{november}/carryover", json={"volume": 100_000, "reason": "Falta"}).status_code == 200

    flagged = finance.put(f"/billing/flights/{november}/carryover/billable", json={"billable": True}).json()

    assert flagged["set_by_name"] == "roles_finance@example.com"


def test_a_carry_over_written_by_trading_names_its_author_and_still_carries_no_billing(
    client_for_roles: Any, test_db_session: Session
) -> None:
    trading: TestClient = _on(client_for_roles("trading"))
    tomas = _named(test_db_session, "trading", "Tomás Ruiz")
    _, _, november = _carry_line(test_db_session)

    response = trading.put(f"/flights/{november}/carryover", json={"volume": 100_000, "reason": "Falta de octubre"})

    body = response.json()
    assert response.status_code == 200
    assert (body["set_by"], body["set_by_name"]) == (tomas, "Tomás Ruiz")
    assert set(body) == CARRYOVER_FIELDS  # no amount, no billable flag, no adjustment and no adjustment reason
