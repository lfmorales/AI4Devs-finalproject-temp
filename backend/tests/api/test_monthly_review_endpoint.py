"""POST /billing/reviews and /billing/reviews/withdrawals, and what reopens a review (finance/monthly-review).

A campaign has, in each month, a state derived from its flights and from its latest review event: in progress while a
flight runs, pending review once they have all ended, reviewed after a review, closed once a closing froze them. Only the
events are stored. The worked case: the August 2026 flight of a committed line, with D-1 on 31 August (it has ended).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.application.services.monthly_review_service import MonthlyReviewService
from app.application.services.delivery_ingestion_service import DeliveryIngestionService
from app.domain.value_objects.delivery import DeliveryDateRange, ExternalLineKey
from app.domain.value_objects.review import ReviewState
from app.infrastructure.persistence.models.campaign import CampaignLinePeriodRecord, CampaignLineRecord
from app.infrastructure.persistence.models.delivery import IngestionBatchRecord
from app.infrastructure.persistence.models.identity import UserRecord
from app.infrastructure.persistence.models.masters import DSPRecord
from app.infrastructure.persistence.models.margin import CampaignPeriodReviewRecord, FlightBillingAdjustmentRecord
from app.infrastructure.persistence.repositories import sqlalchemy_review_repository as review_repository
from app.infrastructure.persistence.repositories.sqlalchemy_review_repository import SqlAlchemyMonthlyReviewTransaction
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import (
    add_line_to_campaign,
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    insert_mapping,
    insert_other_dsp,
    replace_flights,
    seeded_dsp_id,
)
from tests.fixtures.delivery_rows import dsp_row
from tests.fixtures.dsp_delivery_client import InMemoryDspDeliveryClient
from tests.fixtures.margin_data import load_months_last_day, make_month_closable, set_volume

OCTOBER = (date(2026, 10, 1), date(2026, 10, 31))
NOVEMBER = (date(2026, 11, 1), date(2026, 11, 30))
AFTER_AUGUST = date(2026, 9, 1)  # D-1 is 31 August: August has ended
AFTER_NOVEMBER = date(2026, 12, 2)  # D-1 is 1 December: October and November have ended
RUNNING = date(2026, 8, 11)  # D-1 is 10 August
REASON = "Acuerdo con la agencia"


def _on(client: TestClient, today: date = AFTER_AUGUST) -> TestClient:
    """Pin D and confirm the data prepared so far: a refused request rolls the service back, and the test session joins
    an outer transaction through a savepoint, so what was only flushed would be lost with it."""
    overrides = client.app.dependency_overrides
    overrides[providers.get_today] = lambda: today
    next(overrides[providers.get_db_session]()).commit()
    return client


def _campaign_of(session: Session, line_id: int) -> int:
    return int(session.get(CampaignLineRecord, line_id).campaign_id)  # type: ignore[union-attr]


def _flight_ids(session: Session, line_id: int) -> list[int]:
    return list(session.scalars(
        select(CampaignLinePeriodRecord.id).where(CampaignLinePeriodRecord.campaign_line_id == line_id)
        .order_by(CampaignLinePeriodRecord.flight_start)
    ))


def _august(session: Session, name: str = "Review", loaded: bool = True) -> tuple[int, int, int]:
    """A campaign with one August flight that delivered 700,000 of its million; returns campaign, line and flight.

    Left `loaded`, its DSP has loaded 31 August, as a review requires; False leaves the day unloaded."""
    line_id = insert_campaign_line(session, campaign_name=name)
    insert_delivery(session, line_id, date(2026, 8, 10), 700_000, insert_ingestion_batch(session), Decimal("1200.00"))
    if loaded:
        load_months_last_day(session, 2026, 8)
    return _campaign_of(session, line_id), line_id, _flight_ids(session, line_id)[0]


def _batch(session: Session, dsp_id: int, status: str, window: tuple[date, date]) -> None:
    session.add(IngestionBatchRecord(
        dsp_id=dsp_id, route="api", source_file=None, started_at=datetime(2026, 9, 1, 6, 15),
        finished_at=datetime(2026, 9, 1, 6, 20), status=status, row_count=0, window_start=window[0],
        window_end=window[1],
    ))
    session.flush()


def _review(client: TestClient, campaign_id: int, month: int = 8, year: int = 2026) -> Any:
    return client.post("/billing/reviews", json={"campaign_id": campaign_id, "year": year, "month": month})


def _withdraw(client: TestClient, campaign_id: int, month: int = 8, year: int = 2026) -> Any:
    return client.post("/billing/reviews/withdrawals", json={"campaign_id": campaign_id, "year": year, "month": month})


def _events(session: Session) -> list[CampaignPeriodReviewRecord]:
    session.expire_all()
    return list(session.scalars(select(CampaignPeriodReviewRecord).order_by(CampaignPeriodReviewRecord.id)))


def _state(session: Session, campaign_id: int, month: int = 8, today: date = AFTER_AUGUST) -> ReviewState:
    service = MonthlyReviewService(SqlAlchemyMonthlyReviewTransaction(session), today=lambda: today, now=datetime.now)
    return service.state(campaign_id, 2026, month)


def _user(session: Session, role: str) -> int:
    return int(session.scalars(select(UserRecord.id).where(UserRecord.email == f"roles_{role}@example.com")).one())


# ---------------------------------------------------------------- marking a campaign reviewed


@pytest.mark.parametrize("role", ["finance", "operations"])
def test_finance_and_operations_review_a_campaign_whose_flights_have_ended(
    client_for_roles: Any, test_db_session: Session, role: str
) -> None:
    campaign, _, _ = _august(test_db_session)
    client = _on(client_for_roles(role))
    assert _state(test_db_session, campaign) is ReviewState.PENDING_REVIEW

    response = _review(client, campaign)

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"campaign_id", "year", "month", "state", "set_by", "set_by_name", "set_at"}
    assert (body["campaign_id"], body["year"], body["month"], body["state"]) == (campaign, 2026, 8, "reviewed")
    assert body["set_by"] == _user(test_db_session, role) and datetime.fromisoformat(body["set_at"])
    (event,) = _events(test_db_session)
    assert (event.kind, event.cause, event.campaign_line_period_id, event.created_by) == ("reviewed", None, None, body["set_by"])
    assert event.created_at.isoformat() == body["set_at"]
    assert _state(test_db_session, campaign) is ReviewState.REVIEWED


def test_a_campaign_with_a_flight_still_running_cannot_be_reviewed(client_for_roles: Any, test_db_session: Session) -> None:
    campaign, line, _ = _august(test_db_session)
    add_line_to_campaign(test_db_session, line, 2)  # a second flight in the same August period, ending on the 31st
    test_db_session.execute(update(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.campaign_line_id == line).values(
        flight_end=date(2026, 8, 15)))

    response = _review(_on(client_for_roles("finance"), date(2026, 8, 21)), campaign)

    assert (response.status_code, response.json()["code"]) == (409, "campaign_month_in_progress")
    assert set(response.json()) == {"code", "message"}
    assert _events(test_db_session) == []
    assert _state(test_db_session, campaign, today=date(2026, 8, 21)) is ReviewState.IN_PROGRESS


def test_a_flight_ending_today_has_not_ended_so_its_campaign_cannot_be_reviewed(
    client_for_roles: Any, test_db_session: Session
) -> None:
    # D is 31 August, the last day of the flight: D-1 is the 30th, the last day counted, so the flight still runs.
    campaign, _, _ = _august(test_db_session)

    response = _review(_on(client_for_roles("finance"), date(2026, 8, 31)), campaign)

    assert (response.status_code, response.json()["code"]) == (409, "campaign_month_in_progress")
    assert _events(test_db_session) == []
    assert _state(test_db_session, campaign, today=date(2026, 8, 31)) is ReviewState.IN_PROGRESS


def test_a_flight_that_ended_yesterday_has_ended_so_its_campaign_can_be_reviewed(
    client_for_roles: Any, test_db_session: Session
) -> None:
    # D is 1 September: D-1 is the 31st, the flight's last day, counted, so the flight has ended.
    campaign, _, _ = _august(test_db_session)

    response = _review(_on(client_for_roles("finance"), date(2026, 9, 1)), campaign)

    assert (response.status_code, response.json()["state"]) == (201, "reviewed")


def _dsp(session: Session, name: str) -> int:
    existing = session.scalars(select(DSPRecord.id).where(DSPRecord.name == name)).first()
    return existing if existing is not None else insert_other_dsp(session, name)


NOT_LOADED = "The delivery of 2026-08 from {dsp} is not loaded up to its last day. Load it, then review the campaign."


def test_a_campaign_whose_dsp_has_not_loaded_the_months_last_day_cannot_be_reviewed(
    client_for_roles: Any, test_db_session: Session
) -> None:
    campaign, _, _ = _august(test_db_session, loaded=False)
    _batch(test_db_session, seeded_dsp_id(test_db_session), "succeeded", (date(2026, 8, 24), date(2026, 8, 30)))
    finance = _on(client_for_roles("finance"))

    response = _review(finance, campaign)

    assert response.status_code == 409
    assert response.json() == {
        "code": "month_delivery_not_loaded", "message": NOT_LOADED.format(dsp="Delivery fixture DSP"),
    }
    assert _events(test_db_session) == []
    assert _state(test_db_session, campaign) is ReviewState.PENDING_REVIEW
    _batch(test_db_session, seeded_dsp_id(test_db_session), "succeeded", (date(2026, 8, 25), date(2026, 8, 31)))
    assert _review(_on(finance), campaign).status_code == 201


def test_a_failed_batch_of_its_dsp_or_a_batch_of_another_dsp_does_not_let_it_be_reviewed(
    client_for_roles: Any, test_db_session: Session
) -> None:
    campaign, _, _ = _august(test_db_session, loaded=False)
    _batch(test_db_session, seeded_dsp_id(test_db_session), "failed", (date(2026, 8, 25), date(2026, 8, 31)))
    _batch(test_db_session, _dsp(test_db_session, "Adform"), "succeeded", (date(2026, 8, 25), date(2026, 8, 31)))

    response = _review(_on(client_for_roles("finance")), campaign)

    assert (response.status_code, response.json()["code"]) == (409, "month_delivery_not_loaded")
    assert _events(test_db_session) == []


def test_every_dsp_of_the_campaign_s_lines_must_have_loaded_the_months_last_day(
    client_for_roles: Any, test_db_session: Session
) -> None:
    campaign, line, _ = _august(test_db_session)  # the fixture DSP has loaded 31 August
    equativ = _dsp(test_db_session, "Equativ")
    second = add_line_to_campaign(test_db_session, line, 2)
    test_db_session.execute(update(CampaignLineRecord).where(CampaignLineRecord.id == second).values(dsp_id=equativ))

    response = _review(_on(client_for_roles("operations")), campaign)

    assert response.json() == {"code": "month_delivery_not_loaded", "message": NOT_LOADED.format(dsp="Equativ")}
    assert _events(test_db_session) == []


def test_a_campaign_already_reviewed_answers_its_review_before_the_delivery_is_checked(
    client_for_roles: Any, test_db_session: Session
) -> None:
    campaign, line, _ = _august(test_db_session)
    finance = _on(client_for_roles("finance"))
    first = _review(finance, campaign).json()
    # A line on a DSP that has not loaded 31 August is added afterwards: the campaign's latest event is still a review.
    second = add_line_to_campaign(test_db_session, line, 2)
    test_db_session.execute(update(CampaignLineRecord).where(CampaignLineRecord.id == second).values(
        dsp_id=_dsp(test_db_session, "Equativ")))

    again = _review(_on(finance), campaign)

    assert (again.status_code, again.json()["set_at"]) == (200, first["set_at"])
    assert len(_events(test_db_session)) == 1


def test_the_flight_counts_take_d_minus_1_as_the_last_day_counted(test_db_session: Session) -> None:
    campaign, _, _ = _august(test_db_session)
    transaction = SqlAlchemyMonthlyReviewTransaction(test_db_session)
    period_id = transaction.period_of(campaign, 2026, 8)
    assert period_id is not None

    assert (transaction.flight_counts(period_id, date(2026, 8, 30)).ended,
            transaction.flight_counts(period_id, date(2026, 8, 31)).ended) == (0, 1)


def test_a_campaign_whose_flights_are_frozen_cannot_be_reviewed(client_for_roles: Any, test_db_session: Session) -> None:
    campaign, _, _ = _august(test_db_session)
    make_month_closable(test_db_session, 2026, 8, None, AFTER_AUGUST)
    finance = _on(client_for_roles("finance"))
    assert finance.post("/margin/closings", json={"year": 2026, "month": 8}).status_code == 200
    reviewed_before_closing = len(_events(test_db_session))

    response = _review(finance, campaign)

    assert (response.status_code, response.json()["code"]) == (409, "campaign_month_closed")
    assert len(_events(test_db_session)) == reviewed_before_closing == 1  # only the review the closing required
    assert _state(test_db_session, campaign) is ReviewState.CLOSED


def test_reviewing_twice_answers_200_with_the_first_review_and_writes_once(
    client_for_roles: Any, test_db_session: Session
) -> None:
    campaign, _, _ = _august(test_db_session)
    finance = _on(client_for_roles("finance"))
    first = _review(finance, campaign)

    again = _review(_on(client_for_roles("operations")), campaign)

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json()
    assert len(_events(test_db_session)) == 1


def test_an_unknown_campaign_is_not_found(client_for_roles: Any, test_db_session: Session) -> None:
    response = _review(_on(client_for_roles("finance")), 999_999)

    assert (response.status_code, response.json()["code"]) == (404, "campaign_not_found")
    assert set(response.json()) == {"code", "message"}


def test_a_campaign_without_flights_in_the_month_is_not_found_in_it(client_for_roles: Any, test_db_session: Session) -> None:
    campaign, _, _ = _august(test_db_session)
    client = _on(client_for_roles("finance"))

    for response in (_review(client, campaign, month=3), _withdraw(client, campaign, month=3)):
        assert (response.status_code, response.json()["code"]) == (404, "campaign_month_not_found")
    assert _events(test_db_session) == []


@pytest.mark.parametrize("payload", [{}, {"campaign_id": 1, "year": 2026}, {"campaign_id": 0, "year": 2026, "month": 8},
                                     {"campaign_id": 1, "year": 2026, "month": 13}, {"campaign_id": 1, "year": 1999, "month": 8},
                                     {"campaign_id": "x", "year": 2026, "month": 8}],
                         ids=["empty", "no-month", "campaign-zero", "month-13", "year-1999", "text"])
def test_a_malformed_request_is_a_validation_error_with_only_code_and_message(
    client_for_roles: Any, payload: dict[str, object]
) -> None:
    client = client_for_roles("finance")

    for path in ("/billing/reviews", "/billing/reviews/withdrawals"):
        response = client.post(path, json=payload)
        assert response.status_code == 422
        assert set(response.json()) == {"code", "message"}


# ---------------------------------------------------------------- withdrawing the review


def test_a_review_is_withdrawn_and_the_withdrawal_stays_in_the_history(client_for_roles: Any, test_db_session: Session) -> None:
    campaign, _, _ = _august(test_db_session)
    _review(_on(client_for_roles("finance")), campaign)

    response = _withdraw(_on(client_for_roles("operations")), campaign)

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["state"], body["set_by"]) == ("pending_review", _user(test_db_session, "operations"))
    assert [(e.kind, e.cause, e.campaign_line_period_id) for e in _events(test_db_session)] == [
        ("reviewed", None, None), ("reopened", "withdrawn", None),
    ]
    assert _state(test_db_session, campaign) is ReviewState.PENDING_REVIEW


def test_a_campaign_can_be_reviewed_again_after_the_withdrawal(client_for_roles: Any, test_db_session: Session) -> None:
    campaign, _, _ = _august(test_db_session)
    finance = _on(client_for_roles("finance"))
    _review(finance, campaign)
    _withdraw(finance, campaign)

    assert _review(finance, campaign).status_code == 201
    assert [e.kind for e in _events(test_db_session)] == ["reviewed", "reopened", "reviewed"]
    assert _state(test_db_session, campaign) is ReviewState.REVIEWED


def test_only_a_reviewed_campaign_can_be_withdrawn(client_for_roles: Any, test_db_session: Session) -> None:
    campaign, _, _ = _august(test_db_session)

    response = _withdraw(_on(client_for_roles("finance")), campaign)

    assert (response.status_code, response.json()["code"]) == (409, "not_reviewed")
    assert _events(test_db_session) == []


def test_a_closed_campaign_month_cannot_be_withdrawn(client_for_roles: Any, test_db_session: Session) -> None:
    campaign, _, _ = _august(test_db_session)
    load_months_last_day(test_db_session, 2026, 8)  # the review is the test's own, through the route
    finance = _on(client_for_roles("finance"))
    _review(finance, campaign)
    assert finance.post("/margin/closings", json={"year": 2026, "month": 8}).status_code == 200

    response = _withdraw(finance, campaign)

    assert (response.status_code, response.json()["code"]) == (409, "campaign_month_closed")
    assert [e.kind for e in _events(test_db_session)] == ["reviewed"]


def test_an_unknown_campaign_cannot_be_withdrawn(client_for_roles: Any, test_db_session: Session) -> None:
    response = _withdraw(_on(client_for_roles("finance")), 999_999)

    assert (response.status_code, response.json()["code"]) == (404, "campaign_not_found")


# ---------------------------------------------------------------- roles


@pytest.mark.parametrize("role", ["trading", "business"])
def test_trading_and_business_can_neither_review_nor_withdraw(client_for_roles: Any, test_db_session: Session, role: str) -> None:
    campaign, _, _ = _august(test_db_session)
    client = _on(client_for_roles(role))

    for response in (_review(client, campaign), _withdraw(client, campaign)):
        assert response.status_code == 403
        assert set(response.json()) == {"code", "message"}
    assert _events(test_db_session) == []


def test_a_request_without_a_token_is_unauthenticated(client: TestClient) -> None:
    assert _review(client, 1).status_code == 401
    assert _withdraw(client, 1).status_code == 401


def test_the_routes_answer_for_real_and_not_501(client_for_roles: Any, test_db_session: Session) -> None:
    campaign, _, _ = _august(test_db_session)
    finance = _on(client_for_roles("finance"))

    assert _review(finance, campaign).status_code != 501
    assert _withdraw(finance, campaign).status_code != 501


# ---------------------------------------------------------------- the month lock


@pytest.mark.parametrize("action", ["review", "withdraw"])
def test_a_review_or_a_withdrawal_takes_the_lock_of_the_month_before_it_writes(
    client_for_roles: Any, test_db_session: Session, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    campaign, _, _ = _august(test_db_session)
    finance = _on(client_for_roles("finance"))
    if action == "withdraw":
        _review(finance, campaign)
    calls: list[str] = []
    transaction = SqlAlchemyMonthlyReviewTransaction
    lock, add = transaction.lock_month, transaction.add_event

    def spy_lock(self: Any, year: int, month: int) -> None:
        calls.append(f"lock {year}-{month:02d}")
        lock(self, year, month)

    def spy_add(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append("add")
        return add(self, *args, **kwargs)

    monkeypatch.setattr(transaction, "lock_month", spy_lock)
    monkeypatch.setattr(transaction, "add_event", spy_add)

    response = (_review if action == "review" else _withdraw)(finance, campaign)

    assert response.status_code == 201
    assert calls == ["lock 2026-08", "add"]


# ---------------------------------------------------------------- what reopens a review


def _reviewed_adjustable(client_for_roles: Any, session: Session) -> tuple[TestClient, int, int, int]:
    campaign, _, flight = _august(session)
    finance = _on(client_for_roles("finance"))
    assert _review(finance, campaign).status_code == 201
    return finance, campaign, flight, _user(session, "finance")


def _adjust(client: TestClient, flight: int, **body: object) -> Any:
    payload: dict[str, object] = {"basis": "contracted", "reason": REASON}
    payload.update(body)
    return client.post(f"/billing/flights/{flight}/adjustments", json=payload)


def test_an_adjustment_reopens_a_reviewed_campaign_with_its_cause_its_flight_and_its_user(
    client_for_roles: Any, test_db_session: Session
) -> None:
    finance, campaign, flight, author = _reviewed_adjustable(client_for_roles, test_db_session)

    assert _adjust(finance, flight).status_code == 201

    reviewed, reopened = _events(test_db_session)
    assert (reviewed.kind, reopened.kind, reopened.cause, reopened.campaign_line_period_id, reopened.created_by) == (
        "reviewed", "reopened", "adjustment", flight, author,
    )
    assert _state(test_db_session, campaign) is ReviewState.PENDING_REVIEW


def test_the_reopening_and_the_adjustment_are_written_in_one_transaction(
    client_for_roles: Any, test_db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    finance, campaign, flight, _ = _reviewed_adjustable(client_for_roles, test_db_session)

    def fail(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("the reopening failed")

    monkeypatch.setattr(review_repository, "reopen_review_if_reviewed", fail)

    with pytest.raises(RuntimeError):
        _adjust(finance, flight)

    test_db_session.expire_all()
    assert test_db_session.scalars(select(FlightBillingAdjustmentRecord)).all() == []
    assert [e.kind for e in _events(test_db_session)] == ["reviewed"]
    assert _state(test_db_session, campaign) is ReviewState.REVIEWED


def test_an_edit_of_a_campaign_pending_review_writes_no_event(client_for_roles: Any, test_db_session: Session) -> None:
    campaign, _, flight = _august(test_db_session)
    finance = _on(client_for_roles("finance"))

    assert _adjust(finance, flight).status_code == 201

    assert _events(test_db_session) == []
    assert _state(test_db_session, campaign) is ReviewState.PENDING_REVIEW


def test_an_adjustment_that_is_refused_does_not_reopen_the_review(client_for_roles: Any, test_db_session: Session) -> None:
    finance, campaign, flight, _ = _reviewed_adjustable(client_for_roles, test_db_session)

    assert _adjust(finance, flight, basis="custom").status_code == 422
    assert _adjust(finance, flight, reason="").status_code == 422

    assert [e.kind for e in _events(test_db_session)] == ["reviewed"]
    assert _state(test_db_session, campaign) is ReviewState.REVIEWED


def test_a_second_edit_of_a_campaign_already_reopened_writes_nothing_more(client_for_roles: Any, test_db_session: Session) -> None:
    finance, _, flight, _ = _reviewed_adjustable(client_for_roles, test_db_session)
    _adjust(finance, flight)

    _adjust(finance, flight, basis="minimum", reason="Vuelta a la regla")

    assert [e.kind for e in _events(test_db_session)] == ["reviewed", "reopened"]


def _carried_line(session: Session) -> tuple[int, int, int]:
    """October delivered 400,000 of 500,000 and November runs on: returns the campaign, the October and the November flight."""
    line_id = insert_campaign_line(session, campaign_name="Carry", start_date=OCTOBER[0], end_date=NOVEMBER[1])
    replace_flights(session, line_id, [OCTOBER, NOVEMBER])
    set_volume(session, line_id, 500_000)
    insert_delivery(session, line_id, date(2026, 10, 10), 400_000, insert_ingestion_batch(session))
    insert_delivery(session, line_id, date(2026, 11, 10), 500_000, insert_ingestion_batch(session))
    for month in (10, 11):  # its DSP has loaded the last day of both months, as a review requires
        load_months_last_day(session, 2026, month)
    october, november = _flight_ids(session, line_id)
    return _campaign_of(session, line_id), october, november


def test_a_carry_over_reopens_a_reviewed_campaign_and_names_the_user_who_wrote_it(
    client_for_roles: Any, test_db_session: Session
) -> None:
    campaign, _, november = _carried_line(test_db_session)
    finance = _on(client_for_roles("finance"), AFTER_NOVEMBER)
    assert _review(finance, campaign, month=11).status_code == 201
    trading = _on(client_for_roles("trading"), AFTER_NOVEMBER)

    response = trading.put(f"/flights/{november}/carryover", json={"volume": 100_000, "reason": "Recuperar octubre"})

    assert response.status_code == 200, response.text
    _, reopened = _events(test_db_session)
    assert (reopened.kind, reopened.cause, reopened.campaign_line_period_id, reopened.created_by) == (
        "reopened", "carryover", november, _user(test_db_session, "trading"),
    )
    assert _state(test_db_session, campaign, month=11, today=AFTER_NOVEMBER) is ReviewState.PENDING_REVIEW


def test_a_change_of_the_billable_flag_reopens_a_reviewed_campaign(client_for_roles: Any, test_db_session: Session) -> None:
    campaign, _, november = _carried_line(test_db_session)
    trading = _on(client_for_roles("trading"), AFTER_NOVEMBER)
    assert trading.put(f"/flights/{november}/carryover", json={"volume": 100_000, "reason": "Recuperar"}).status_code == 200
    finance = _on(client_for_roles("finance"), AFTER_NOVEMBER)
    assert _review(finance, campaign, month=11).status_code == 201

    response = finance.put(f"/billing/flights/{november}/carryover/billable", json={"billable": True})

    assert response.status_code == 200, response.text
    reviewed, reopened = _events(test_db_session)
    assert (reviewed.kind, reopened.cause, reopened.campaign_line_period_id, reopened.created_by) == (
        "reviewed", "carryover_billable", november, _user(test_db_session, "finance"),
    )


def test_a_carry_over_that_is_refused_does_not_reopen_the_review(client_for_roles: Any, test_db_session: Session) -> None:
    campaign, _, november = _carried_line(test_db_session)
    finance = _on(client_for_roles("finance"), AFTER_NOVEMBER)
    assert _review(finance, campaign, month=11).status_code == 201
    trading = _on(client_for_roles("trading"), AFTER_NOVEMBER)

    response = trading.put(f"/flights/{november}/carryover", json={"volume": 100_001, "reason": "Demasiado"})

    assert response.status_code == 409
    assert [e.kind for e in _events(test_db_session)] == ["reviewed"]


def test_a_carry_over_reopens_only_the_month_of_the_flight_that_receives_it(client_for_roles: Any, test_db_session: Session) -> None:
    campaign, _, november = _carried_line(test_db_session)
    finance = _on(client_for_roles("finance"), AFTER_NOVEMBER)
    assert _review(finance, campaign, month=10).status_code == 201
    assert _review(finance, campaign, month=11).status_code == 201

    _on(client_for_roles("trading"), AFTER_NOVEMBER).put(
        f"/flights/{november}/carryover", json={"volume": 100_000, "reason": "Recuperar"})

    assert _state(test_db_session, campaign, month=10, today=AFTER_NOVEMBER) is ReviewState.REVIEWED
    assert _state(test_db_session, campaign, month=11, today=AFTER_NOVEMBER) is ReviewState.PENDING_REVIEW


# ---------------------------------------------------------------- what does not


def test_an_ingestion_does_not_reopen_a_review(client_for_roles: Any, test_db_session: Session) -> None:
    campaign, line, _ = _august(test_db_session)
    insert_mapping(test_db_session, line, seeded_dsp_id(test_db_session), "1001", "2001")
    finance = _on(client_for_roles("finance"))
    assert _review(finance, campaign).status_code == 201
    before = [(e.id, e.kind) for e in _events(test_db_session)]
    key = ExternalLineKey("1001", "2001")
    rows = [dsp_row(date(2026, 8, 10), key, impressions=1_300_000, media_cost=Decimal("2500.00"))]

    # The whole of August is ingested again, with other figures, through the ingestion service.
    result = DeliveryIngestionService(
        InMemoryDspDeliveryClient(rows), lambda: SqlAlchemyUnitOfWork(lambda: test_db_session),
        lambda: datetime(2026, 9, 2, 2, 0),
    ).run(seeded_dsp_id(test_db_session), date(2026, 9, 2), window=DeliveryDateRange(date(2026, 8, 1), date(2026, 8, 31)))

    assert result.stored_row_count == 1
    assert [(e.id, e.kind) for e in _events(test_db_session)] == before
    assert _state(test_db_session, campaign) is ReviewState.REVIEWED
    assert _review(_on(client_for_roles("operations")), campaign).status_code == 200


def test_reading_the_margin_does_not_reopen_a_review(client_for_roles: Any, test_db_session: Session) -> None:
    campaign, _, _ = _august(test_db_session)
    finance = _on(client_for_roles("finance"))
    _review(finance, campaign)

    assert finance.get("/margin").status_code == 200

    assert [e.kind for e in _events(test_db_session)] == ["reviewed"]


def test_a_flight_registered_after_the_review_that_has_not_ended_puts_the_campaign_back_in_progress(
    client_for_roles: Any, test_db_session: Session
) -> None:
    campaign, line, _ = _august(test_db_session)
    finance = _on(client_for_roles("finance"))
    _review(finance, campaign)
    add_line_to_campaign(test_db_session, line, 2)  # a second August flight, ending on the 31st
    test_db_session.commit()

    assert _state(test_db_session, campaign, today=date(2026, 8, 25)) is ReviewState.IN_PROGRESS
    assert _state(test_db_session, campaign) is ReviewState.REVIEWED
    assert [e.kind for e in _events(test_db_session)] == ["reviewed"]
