"""POST /margin/closings: freezes the rates of the flights that ended in a month; finance only."""

from datetime import date

import pytest
from sqlalchemy import func, select

from app.infrastructure.persistence.models.margin import AppliedRateRecord
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import add_line_to_campaign, insert_campaign_line, replace_flights

D = date(2026, 9, 1)  # as_of is 31 August: August has ended


@pytest.fixture
def finance_client(client_for_roles):
    client = client_for_roles("finance")
    client.app.dependency_overrides[providers.get_today] = lambda: D
    return client


def _count(session) -> int:
    return session.scalar(select(func.count()).select_from(AppliedRateRecord))


def _august_with_three_lines(session) -> None:
    first = insert_campaign_line(session)
    add_line_to_campaign(session, first, 2)
    add_line_to_campaign(session, first, 3)


def _close(client, year: int = 2026, month: int = 8):
    return client.post("/margin/closings", json={"year": year, "month": month})


def test_finance_closes_a_month_and_gets_the_counts(finance_client, test_db_session):
    _august_with_three_lines(test_db_session)

    response = _close(finance_client)

    assert response.status_code == 200
    assert response.json() == {"year": 2026, "month": 8, "closed": 3, "already_closed": 0}
    assert _count(test_db_session) == 3


def test_closing_again_changes_nothing(finance_client, test_db_session):
    _august_with_three_lines(test_db_session)
    _close(finance_client)

    response = _close(finance_client)

    assert response.status_code == 200
    assert response.json() == {"year": 2026, "month": 8, "closed": 0, "already_closed": 3}
    assert _count(test_db_session) == 3


def test_a_month_without_ended_flights_answers_200_with_zero_closed(finance_client, test_db_session):
    response = _close(finance_client, month=3)

    assert response.status_code == 200
    assert response.json()["closed"] == 0
    assert _count(test_db_session) == 0


def test_an_earlier_open_month_is_a_conflict_that_names_it(finance_client, test_db_session):
    line_id = insert_campaign_line(test_db_session, start_date=date(2026, 6, 1), end_date=date(2026, 8, 31))
    replace_flights(test_db_session, line_id, [(date(2026, 6, 1), date(2026, 6, 30)), (date(2026, 8, 1), date(2026, 8, 31))])

    response = _close(finance_client)

    assert response.status_code == 409
    assert set(response.json()) == {"code", "message"}
    assert response.json()["code"] == "previous_month_open"
    assert "2026-06" in response.json()["message"]
    assert _count(test_db_session) == 0


@pytest.mark.parametrize("body", [
    {"year": 2026, "month": 13}, {"year": 2026, "month": 0}, {"year": "soon", "month": 8},
    {"year": 2026}, {}, {"year": 1899, "month": 1},
])
def test_an_invalid_request_is_code_and_message_only(finance_client, body):
    response = finance_client.post("/margin/closings", json=body)

    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}
    assert response.json()["code"] == "validation_error"


def test_a_method_not_allowed_under_margin_is_code_and_message_too(finance_client):
    response = finance_client.get("/margin/closings")

    assert response.status_code == 405
    assert set(response.json()) == {"code", "message"}


def test_the_counts_are_integers_not_floats(finance_client, test_db_session):
    _august_with_three_lines(test_db_session)

    body = _close(finance_client).json()

    assert all(type(body[key]) is int for key in ("year", "month", "closed", "already_closed"))


@pytest.mark.parametrize("roles", [("operations",), ("business",), ("operations", "business"), ()])
def test_a_user_without_finance_is_forbidden_and_nothing_is_written(client_for_roles, test_db_session, roles):
    _august_with_three_lines(test_db_session)
    client = client_for_roles(*roles)
    client.app.dependency_overrides[providers.get_today] = lambda: D

    response = _close(client)

    assert response.status_code == 403
    assert set(response.json()) == {"code", "message"}
    assert _count(test_db_session) == 0


def test_a_user_holding_finance_among_other_roles_may_close(client_for_roles, test_db_session):
    _august_with_three_lines(test_db_session)
    client = client_for_roles("operations", "finance")
    client.app.dependency_overrides[providers.get_today] = lambda: D

    assert _close(client).status_code == 200


def test_a_request_without_a_token_is_unauthenticated(client):
    response = client.post("/margin/closings", json={"year": 2026, "month": 8})

    assert response.status_code == 401
    assert set(response.json()) == {"code", "message"}


def test_campaign_registration_keeps_its_own_validation_format(authenticated_client):
    response = authenticated_client.post("/campaigns", json={})

    assert response.status_code == 422
    assert "detail" in response.json()
    assert "code" not in response.json()
