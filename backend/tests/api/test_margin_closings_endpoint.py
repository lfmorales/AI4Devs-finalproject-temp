"""POST /margin/closings: freezes the rates of the flights that ended in a month; operations and finance only."""

from datetime import date, datetime
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.campaign import CampaignLineRecord
from app.infrastructure.persistence.models.delivery import IngestionBatchRecord
from app.infrastructure.persistence.models.margin import AppliedRateRecord
from app.infrastructure.persistence.models.masters import DSPRecord
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import add_line_to_campaign, insert_campaign_line, insert_other_dsp, replace_flights

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
    assert response.json() == {"year": 2026, "month": 8, "closed": 3, "already_closed": 0, "closings": 1}
    assert _count(test_db_session) == 3


def test_closing_again_changes_nothing(finance_client, test_db_session):
    _august_with_three_lines(test_db_session)
    _close(finance_client)

    response = _close(finance_client)

    assert response.status_code == 200
    assert response.json() == {"year": 2026, "month": 8, "closed": 0, "already_closed": 3, "closings": 1}
    assert _count(test_db_session) == 3


def test_a_month_without_ended_flights_answers_200_with_zero_closed(finance_client, test_db_session):
    response = _close(finance_client, month=3)

    assert response.status_code == 200
    assert (response.json()["closed"], response.json()["closings"]) == (0, 0)
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


def _august_target_line_on_equativ(session: Session) -> None:
    """A target line on Equativ whose August flight ended; Equativ has loaded only up to 30 August."""
    existing = session.scalars(select(DSPRecord.id).where(DSPRecord.name == "Equativ")).first()
    equativ = existing if existing is not None else insert_other_dsp(session, "Equativ")
    line_id = insert_campaign_line(session, "Equativ target", dsp_id=equativ)
    session.execute(update(CampaignLineRecord).where(CampaignLineRecord.id == line_id).values(volume_commitment="target"))
    session.add(IngestionBatchRecord(
        dsp_id=equativ, route="api", source_file=None, started_at=datetime(2026, 8, 31, 6, 15),
        finished_at=datetime(2026, 8, 31, 6, 20), status="succeeded", row_count=0,
        window_start=date(2026, 8, 24), window_end=date(2026, 8, 30),
    ))
    session.flush()


def test_a_month_whose_target_flights_dsp_has_not_loaded_its_last_day_is_a_conflict_that_names_both(
    finance_client: Any, test_db_session: Session
) -> None:
    _august_target_line_on_equativ(test_db_session)

    response = _close(finance_client)

    assert response.status_code == 409
    assert response.json() == {
        "code": "month_delivery_not_loaded",
        "message": "The delivery of 2026-08 from Equativ is not loaded up to its last day. Load it, then close the month.",
    }
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

    assert all(type(body[key]) is int for key in ("year", "month", "closed", "already_closed", "closings"))


def test_a_flight_registered_in_a_closed_month_is_closed_by_a_second_closing_that_answers_two_closings(
    finance_client: Any, test_db_session: Session
) -> None:
    first = insert_campaign_line(test_db_session)
    _close(finance_client)
    add_line_to_campaign(test_db_session, first, 2)

    response = _close(finance_client)

    assert response.status_code == 200
    assert response.json() == {"year": 2026, "month": 8, "closed": 1, "already_closed": 1, "closings": 2}


@pytest.mark.parametrize(
    ("role", "status"), [("operations", 200), ("finance", 200), ("business", 403), ("trading", 403)]
)
def test_each_role_gets_the_outcome_of_the_access_matrix(client_for_roles, test_db_session, role, status):
    _august_with_three_lines(test_db_session)
    client = client_for_roles(role)
    client.app.dependency_overrides[providers.get_today] = lambda: D

    response = _close(client)

    assert response.status_code == status
    if status == 403:
        assert set(response.json()) == {"code", "message"}
        assert _count(test_db_session) == 0
    else:
        assert _count(test_db_session) == 3


@pytest.mark.parametrize("roles", [(), ("business", "trading")])
def test_a_user_without_operations_or_finance_is_forbidden_and_nothing_is_written(client_for_roles, test_db_session, roles):
    _august_with_three_lines(test_db_session)
    client = client_for_roles(*roles)
    client.app.dependency_overrides[providers.get_today] = lambda: D

    assert _close(client).status_code == 403
    assert _count(test_db_session) == 0


def test_a_user_holding_an_accepted_role_among_others_may_close(client_for_roles, test_db_session):
    _august_with_three_lines(test_db_session)
    client = client_for_roles("trading", "finance")
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
