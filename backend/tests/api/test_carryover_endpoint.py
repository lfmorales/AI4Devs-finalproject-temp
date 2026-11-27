"""PUT /flights/{id}/carryover and PUT /billing/flights/{id}/carryover/billable (campaign/carryover).

The worked example: a committed line at 5.00 € with an October 2026 flight of 500,000 impressions that delivered
400,000 and a November flight of 500,000, with D-1 on 5 November. Trading and operations write the carry-over;
operations and finance decide whether it is billable. Nothing here is ever an amount.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.campaign import CampaignLinePeriodRecord, CampaignLineRecord
from app.infrastructure.persistence.models.identity import UserRecord
from app.infrastructure.persistence.models.margin import MonthClosingRecord
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import (
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    replace_flights,
)
from tests.fixtures.margin_data import set_volume

OCTOBER = (date(2026, 10, 1), date(2026, 10, 31))
NOVEMBER = (date(2026, 11, 1), date(2026, 11, 30))
D_PLUS_1 = date(2026, 11, 6)  # D-1 is 5 November: October has ended, November runs
REASON = "Recuperar lo no entregado en octubre"
RESPONSE_FIELDS = {
    "flight_id", "delivery_metric", "contracted_impressions", "carryover", "delivery_target", "reason", "set_by",
    "set_by_name", "set_at",
}
BILLABLE_FIELDS = {"flight_id", "carryover", "billable", "set_by", "set_by_name", "set_at"}
FORBIDDEN_WORDS = ("billable", "amount", "revenue", "cost", "margin", "rebate", "price", "cpm", "adjust")


def _on(client: TestClient, today: date = D_PLUS_1) -> TestClient:
    """Pin D and confirm the data prepared so far.

    The test session joins an outer transaction through a savepoint, and a refused request makes the service roll back:
    what was only flushed would be lost with it, so the preparation is committed before the requests start.
    """
    overrides = client.app.dependency_overrides
    overrides[providers.get_today] = lambda: today
    next(overrides[providers.get_db_session]()).commit()
    return client


def _flight_ids(session: Session, line_id: int) -> list[int]:
    return list(session.scalars(
        select(CampaignLinePeriodRecord.id).where(CampaignLinePeriodRecord.campaign_line_id == line_id)
        .order_by(CampaignLinePeriodRecord.flight_start)
    ))


def _line(session: Session, windows: list[tuple[date, date]] | None = None, delivered_before: int = 400_000,
          name: str = "Carry-over") -> tuple[int, list[int]]:
    """A line of 500,000 per flight; its first flight delivered `delivered_before`."""
    windows = windows or [OCTOBER, NOVEMBER]
    line_id = insert_campaign_line(session, campaign_name=name, start_date=windows[0][0], end_date=windows[-1][1])
    replace_flights(session, line_id, windows)
    set_volume(session, line_id, 500_000)
    insert_delivery(session, line_id, windows[0][0], delivered_before, insert_ingestion_batch(session))
    return line_id, _flight_ids(session, line_id)


def _put(client: TestClient, flight_id: int, volume: object = 100_000, reason: object = REASON) -> Any:
    return client.put(f"/flights/{flight_id}/carryover", json={"volume": volume, "reason": reason})


def _flight(session: Session, flight_id: int) -> CampaignLinePeriodRecord:
    session.expire_all()
    return session.get(CampaignLinePeriodRecord, flight_id)  # type: ignore[return-value]


def _state(session: Session, flight_id: int) -> tuple[object, ...]:
    flight = _flight(session, flight_id)
    return (
        flight.carryover, flight.carryover_reason, flight.carryover_set_by, flight.carryover_set_at,
        flight.carryover_billable, flight.carryover_billable_set_by, flight.carryover_billable_set_at,
    )


def _close(session: Session, year: int, month: int) -> None:
    user_id = session.scalars(select(UserRecord.id)).first()
    session.add(MonthClosingRecord(
        period_year=year, period_month=month, closed_at=datetime(2026, 12, 1, 9), closed_by=user_id,
        as_of=date(2026, 11, 30),
    ))
    session.flush()


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


# ---------------------------------------------------------------- PUT /flights/{id}/carryover


@pytest.mark.parametrize("role", ["trading", "operations"])
def test_undelivered_october_volume_is_carried_to_november(client_for_roles: Any, test_db_session: Session, role: str) -> None:
    _, (october, november) = _line(test_db_session)
    client = _on(client_for_roles(role))

    response = _put(client, november)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == RESPONSE_FIELDS
    assert (body["flight_id"], body["delivery_metric"], body["contracted_impressions"]) == (november, "impressions", 500_000)
    assert (body["carryover"], body["delivery_target"], body["reason"]) == (100_000, 600_000, REASON)
    assert isinstance(body["set_by"], int) and datetime.fromisoformat(body["set_at"])
    assert _flight(test_db_session, october).carryover == 0


def test_the_carry_over_is_stored_with_its_reason_its_author_and_its_moment(
    client_for_roles: Any, test_db_session: Session
) -> None:
    _, (_, november) = _line(test_db_session)
    client = _on(client_for_roles("trading"))
    author = test_db_session.scalars(select(UserRecord.id).where(UserRecord.email == "roles_trading@example.com")).one()

    body = _put(client, november).json()

    stored = _flight(test_db_session, november)
    assert (stored.carryover, stored.carryover_reason, stored.carryover_set_by) == (100_000, REASON, author)
    assert stored.carryover_set_at is not None and body["set_by"] == author
    assert body["set_at"] == stored.carryover_set_at.isoformat()


def test_the_contracted_volume_of_the_flight_and_of_the_line_do_not_change(
    client_for_roles: Any, test_db_session: Session
) -> None:
    line_id, (_, november) = _line(test_db_session)

    _put(_on(client_for_roles("operations")), november)

    assert _flight(test_db_session, november).contracted_impressions == 500_000
    assert test_db_session.get(CampaignLineRecord, line_id).contracted_impressions == 500_000  # type: ignore[union-attr]


def test_the_response_to_trading_carries_volumes_and_the_reason_and_no_flag_or_amount(
    client_for_roles: Any, test_db_session: Session
) -> None:
    _, (_, november) = _line(test_db_session)

    body = _put(_on(client_for_roles("trading")), november).json()

    assert not [name for name in _keys(body) if any(word in name.lower() for word in FORBIDDEN_WORDS)]
    assert "billable" not in body


def test_the_carry_over_cannot_exceed_the_shortfall(client_for_roles: Any, test_db_session: Session) -> None:
    _, (_, november) = _line(test_db_session)
    client = _on(client_for_roles("trading"))

    response = _put(client, november, volume=100_001)

    assert response.status_code == 409
    assert set(response.json()) == {"code", "message"}
    assert response.json()["code"] == "carryover_exceeds_shortfall"
    assert "100000" in response.json()["message"]
    assert _flight(test_db_session, november).carryover == 0


def test_a_previous_flight_that_delivered_its_target_leaves_nothing_to_carry(
    client_for_roles: Any, test_db_session: Session
) -> None:
    _, (_, november) = _line(test_db_session, delivered_before=520_000)

    response = _put(_on(client_for_roles("trading")), november, volume=1)

    assert (response.status_code, response.json()["code"]) == (409, "carryover_exceeds_shortfall")
    assert "0" in response.json()["message"]


def test_the_shortfall_counts_the_carry_over_the_previous_flight_received(
    client_for_roles: Any, test_db_session: Session
) -> None:
    # October received 50,000 from September: 550,000 to deliver, 480,000 delivered, so at most 70,000 go to November.
    september = (date(2026, 9, 1), date(2026, 9, 30))
    line_id, (_, october, november) = _line(test_db_session, [september, OCTOBER, NOVEMBER], delivered_before=500_000)
    operations = client_for_roles("operations")
    author = test_db_session.scalars(select(UserRecord.id)).first()
    test_db_session.execute(update(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.id == october).values(
        carryover=50_000, carryover_reason="x", carryover_set_by=author, carryover_set_at=datetime(2026, 10, 2),
    ))
    insert_delivery(test_db_session, line_id, date(2026, 10, 10), 480_000, insert_ingestion_batch(test_db_session))
    client = _on(operations)

    too_much = _put(client, november, volume=70_001)
    enough = _put(client, november, volume=70_000)

    assert (too_much.status_code, too_much.json()["code"]) == (409, "carryover_exceeds_shortfall")
    assert (enough.status_code, enough.json()["carryover"], enough.json()["delivery_target"]) == (200, 70_000, 570_000)


def test_december_carries_to_january(client_for_roles: Any, test_db_session: Session) -> None:
    december = (date(2026, 12, 1), date(2026, 12, 31))
    january = (date(2027, 1, 1), date(2027, 1, 31))
    _, (_, jan) = _line(test_db_session, [december, january], delivered_before=450_000)

    response = _put(_on(client_for_roles("trading"), date(2027, 1, 5)), jan, volume=50_000)

    assert (response.status_code, response.json()["delivery_target"]) == (200, 550_000)


def test_the_first_flight_of_a_line_has_nothing_to_receive(client_for_roles: Any, test_db_session: Session) -> None:
    _, (october, _) = _line(test_db_session)

    response = _put(_on(client_for_roles("trading")), october)

    assert (response.status_code, response.json()["code"]) == (409, "no_previous_flight")
    assert set(response.json()) == {"code", "message"}


def test_the_previous_flight_must_have_ended(client_for_roles: Any, test_db_session: Session) -> None:
    _, (_, november) = _line(test_db_session)

    response = _put(_on(client_for_roles("trading"), date(2026, 10, 20)), november)

    assert (response.status_code, response.json()["code"]) == (409, "previous_flight_not_ended")
    assert _flight(test_db_session, november).carryover == 0


def test_a_closed_month_receives_no_carry_over(client_for_roles: Any, test_db_session: Session) -> None:
    _, (_, november) = _line(test_db_session)
    client_for_roles("operations")
    _close(test_db_session, 2026, 11)

    response = _put(_on(client_for_roles("trading")), november)

    assert (response.status_code, response.json()["code"]) == (409, "month_closed")
    assert set(response.json()) == {"code", "message"}
    assert _flight(test_db_session, november).carryover == 0


@pytest.mark.parametrize("reason", ["", "   "], ids=["empty", "spaces"])
def test_the_reason_is_mandatory(client_for_roles: Any, test_db_session: Session, reason: str) -> None:
    _, (_, november) = _line(test_db_session)

    response = _put(_on(client_for_roles("trading")), november, reason=reason)

    assert (response.status_code, response.json()["code"]) == (422, "invalid_carryover")
    assert set(response.json()) == {"code", "message"}
    assert _state(test_db_session, november)[0] == 0


@pytest.mark.parametrize("payload", [{"volume": 1}, {"reason": REASON}, {}, {"volume": 1.5, "reason": REASON},
                                     {"volume": "1", "reason": REASON}, {"volume": True, "reason": REASON}],
                         ids=["no-reason", "no-volume", "empty", "fraction", "text", "boolean"])
def test_a_malformed_body_is_a_validation_error_with_only_code_and_message(
    client_for_roles: Any, test_db_session: Session, payload: dict[str, object]
) -> None:
    _, (_, november) = _line(test_db_session)

    response = _on(client_for_roles("trading")).put(f"/flights/{november}/carryover", json=payload)

    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}


def test_a_negative_volume_is_refused(client_for_roles: Any, test_db_session: Session) -> None:
    _, (_, november) = _line(test_db_session)

    response = _put(_on(client_for_roles("trading")), november, volume=-1)

    assert (response.status_code, response.json()["code"]) == (422, "invalid_carryover")


def test_a_volume_of_zero_removes_the_carry_over_and_keeps_its_reason_author_and_moment(
    client_for_roles: Any, test_db_session: Session
) -> None:
    _, (_, november) = _line(test_db_session)
    client = _on(client_for_roles("trading"))
    assert _put(client, november).status_code == 200

    response = _put(client, november, volume=0, reason="Ya no hace falta")

    assert response.status_code == 200
    assert (response.json()["carryover"], response.json()["delivery_target"]) == (0, 500_000)
    stored = _flight(test_db_session, november)
    assert (stored.carryover, stored.carryover_reason) == (0, "Ya no hace falta")
    assert stored.carryover_set_by is not None and stored.carryover_set_at is not None


def test_a_carry_over_replaces_the_previous_one(client_for_roles: Any, test_db_session: Session) -> None:
    _, (_, november) = _line(test_db_session)
    client = _on(client_for_roles("trading"))
    _put(client, november, volume=100_000)

    response = _put(client, november, volume=40_000, reason="Menos de lo previsto")

    assert (response.json()["carryover"], response.json()["reason"]) == (40_000, "Menos de lo previsto")


def test_an_unknown_flight_is_not_found(client_for_roles: Any, test_db_session: Session) -> None:
    response = _put(_on(client_for_roles("trading")), 999_999)

    assert (response.status_code, response.json()["code"]) == (404, "flight_not_found")
    assert set(response.json()) == {"code", "message"}


def test_a_target_line_may_receive_a_carry_over(client_for_roles: Any, test_db_session: Session) -> None:
    line_id, (_, november) = _line(test_db_session)
    test_db_session.execute(
        update(CampaignLineRecord).where(CampaignLineRecord.id == line_id).values(volume_commitment="target")
    )

    response = _put(_on(client_for_roles("trading")), november)

    assert (response.status_code, response.json()["delivery_target"]) == (200, 600_000)


@pytest.mark.parametrize("role", ["finance", "business"])
def test_finance_and_business_cannot_write_a_carry_over(client_for_roles: Any, test_db_session: Session, role: str) -> None:
    _, (_, november) = _line(test_db_session)

    response = _put(_on(client_for_roles(role)), november)

    assert response.status_code == 403
    assert set(response.json()) == {"code", "message"}
    assert _flight(test_db_session, november).carryover == 0


def test_a_request_without_a_token_is_unauthenticated(client: TestClient) -> None:
    assert _put(client, 1).status_code == 401


def test_the_route_answers_for_real_and_not_501(client_for_roles: Any, test_db_session: Session) -> None:
    _, (_, november) = _line(test_db_session)

    assert _put(_on(client_for_roles("operations")), november).status_code != 501


def test_the_carry_over_shows_in_the_daily_status_as_the_delivery_target(
    client_for_roles: Any, test_db_session: Session
) -> None:
    _, (_, november) = _line(test_db_session)
    trading = _on(client_for_roles("trading"), D_PLUS_1)
    _put(trading, november)

    [row] = [r for r in trading.get("/campaign-status").json() if r["flight"]["id"] == november]

    assert (row["contracted_impressions"], row["carryover"], row["delivery_target"]) == (500_000, 100_000, 600_000)


def test_the_billable_flag_is_not_changed_by_a_new_volume(client_for_roles: Any, test_db_session: Session) -> None:
    _, (_, november) = _line(test_db_session)
    finance = _on(client_for_roles("finance"))
    trading = _on(client_for_roles("trading"))
    _put(trading, november)
    assert _billable(finance, november, True).status_code == 200

    _put(trading, november, volume=60_000)

    assert _flight(test_db_session, november).carryover_billable is True


# ---------------------------------------------------------------- PUT /billing/flights/{id}/carryover/billable


def _billable(client: TestClient, flight_id: int, billable: object = True) -> Any:
    return client.put(f"/billing/flights/{flight_id}/carryover/billable", json={"billable": billable})


@pytest.mark.parametrize("role", ["finance", "operations"])
def test_finance_and_operations_set_the_carry_over_billable(client_for_roles: Any, test_db_session: Session, role: str) -> None:
    _, (_, november) = _line(test_db_session)
    _put(_on(client_for_roles("trading")), november)
    client = _on(client_for_roles(role))

    response = _billable(client, november)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == BILLABLE_FIELDS
    assert (body["flight_id"], body["carryover"], body["billable"]) == (november, 100_000, True)
    stored = _flight(test_db_session, november)
    author = test_db_session.scalars(select(UserRecord.id).where(UserRecord.email == f"roles_{role}@example.com")).one()
    assert (stored.carryover_billable, stored.carryover_billable_set_by) == (True, author)
    assert stored.carryover_billable_set_at is not None and body["set_by"] == author


def test_setting_the_flag_does_not_touch_the_volume_its_reason_or_its_author(
    client_for_roles: Any, test_db_session: Session
) -> None:
    _, (_, november) = _line(test_db_session)
    _put(_on(client_for_roles("trading")), november)
    before = _state(test_db_session, november)[:4]

    _billable(_on(client_for_roles("finance")), november)

    assert _state(test_db_session, november)[:4] == before


def test_the_flag_defaults_to_false_and_can_be_set_back_to_false(client_for_roles: Any, test_db_session: Session) -> None:
    _, (_, november) = _line(test_db_session)
    _put(_on(client_for_roles("trading")), november)
    assert _flight(test_db_session, november).carryover_billable is False
    finance = _on(client_for_roles("finance"))
    _billable(finance, november, True)

    response = _billable(finance, november, False)

    assert (response.status_code, response.json()["billable"]) == (200, False)
    assert _flight(test_db_session, november).carryover_billable is False


@pytest.mark.parametrize("role", ["trading", "business"])
def test_trading_and_business_cannot_set_the_flag(client_for_roles: Any, test_db_session: Session, role: str) -> None:
    _, (_, november) = _line(test_db_session)
    _put(_on(client_for_roles("operations")), november)

    response = _billable(_on(client_for_roles(role)), november)

    assert response.status_code == 403
    assert set(response.json()) == {"code", "message"}
    assert not any(word in response.text.lower() for word in ("amount", "revenue", "billable"))
    assert _flight(test_db_session, november).carryover_billable is False


def test_the_flag_needs_a_token(client: TestClient) -> None:
    assert _billable(client, 1).status_code == 401


def test_the_flag_of_a_target_line_is_refused(client_for_roles: Any, test_db_session: Session) -> None:
    line_id, (_, november) = _line(test_db_session)
    _put(_on(client_for_roles("trading")), november)
    test_db_session.execute(
        update(CampaignLineRecord).where(CampaignLineRecord.id == line_id).values(volume_commitment="target")
    )

    response = _billable(_on(client_for_roles("finance")), november)

    assert (response.status_code, response.json()["code"]) == (409, "target_line_not_adjustable")
    assert set(response.json()) == {"code", "message"}
    assert _flight(test_db_session, november).carryover_billable is False


def test_there_must_be_something_to_bill(client_for_roles: Any, test_db_session: Session) -> None:
    _, (_, november) = _line(test_db_session)

    response = _billable(_on(client_for_roles("finance")), november)

    assert (response.status_code, response.json()["code"]) == (409, "no_carryover")
    assert _flight(test_db_session, november).carryover_billable is False


def test_the_flag_of_a_closed_month_is_refused(client_for_roles: Any, test_db_session: Session) -> None:
    _, (_, november) = _line(test_db_session)
    _put(_on(client_for_roles("trading")), november)
    _close(test_db_session, 2026, 11)

    response = _billable(_on(client_for_roles("finance")), november)

    assert (response.status_code, response.json()["code"]) == (409, "month_closed")
    assert _flight(test_db_session, november).carryover_billable is False


def test_the_flag_of_an_unknown_flight_is_not_found(client_for_roles: Any, test_db_session: Session) -> None:
    response = _billable(_on(client_for_roles("finance")), 999_999)

    assert (response.status_code, response.json()["code"]) == (404, "flight_not_found")


@pytest.mark.parametrize("payload", [{}, {"billable": "yes"}, {"billable": 1}], ids=["empty", "text", "number"])
def test_a_malformed_flag_body_is_a_validation_error(client_for_roles: Any, test_db_session: Session, payload: dict[str, object]) -> None:
    _, (_, november) = _line(test_db_session)

    response = _on(client_for_roles("finance")).put(f"/billing/flights/{november}/carryover/billable", json=payload)

    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}


def test_the_billable_route_answers_for_real_and_not_501(client_for_roles: Any, test_db_session: Session) -> None:
    _, (_, november) = _line(test_db_session)

    assert _billable(_on(client_for_roles("finance")), november).status_code != 501


def test_the_amount_of_a_carry_over_is_never_a_decimal_anywhere(client_for_roles: Any, test_db_session: Session) -> None:
    _, (_, november) = _line(test_db_session)
    body = _put(_on(client_for_roles("trading")), november).json()

    assert not [value for value in body.values() if isinstance(value, (float, Decimal))]
