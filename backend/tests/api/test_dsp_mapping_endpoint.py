"""POST /campaign-lines/{id}/dsp-mappings: operations only, three validation outcomes, global error bodies."""

from datetime import date
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.exceptions import DspAuthenticationError, DspUnreachableError
from app.domain.value_objects.catalog import CatalogLineObservation
from app.domain.value_objects.delivery import ExternalLineKey
from app.infrastructure.persistence.repositories.sqlalchemy_dsp_catalog_repository import (
    SqlAlchemyDspCatalogRepository,
)
from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord
from app.infrastructure.persistence.models.masters import DSPRecord
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import insert_campaign_line, seeded_dsp_id
from tests.fixtures.dsp_delivery_client import ScriptedDspDeliveryClient

KEY = ExternalLineKey("1001", "2001")
BODY = {"external_campaign_id": "1001", "external_line_item_id": "2001"}


def _use_dsp_client(client, dsp_client: ScriptedDspDeliveryClient | None) -> None:
    client.app.dependency_overrides[providers.get_dsp_client_resolver] = lambda: (lambda dsp_name: dsp_client)


def _post(client, line_id: int, body: dict = BODY):
    return client.post(f"/campaign-lines/{line_id}/dsp-mappings", json=body)


@pytest.fixture
def line_id(test_db_session) -> int:
    return insert_campaign_line(test_db_session)


def test_a_found_pair_creates_a_validated_mapping(authenticated_client, line_id):
    _use_dsp_client(authenticated_client, ScriptedDspDeliveryClient(KEY))

    response = _post(authenticated_client, line_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["validation"], body["campaign_line_id"]) == ("found", line_id)
    assert (body["external_campaign_id"], body["external_line_item_id"]) == ("1001", "2001")
    assert body["validated_at"] is not None


def test_an_unknown_pair_creates_an_unvalidated_mapping(authenticated_client, line_id):
    _use_dsp_client(authenticated_client, ScriptedDspDeliveryClient(None))

    response = _post(authenticated_client, line_id)

    assert response.status_code == 201
    assert (response.json()["validation"], response.json()["validated_at"]) == ("unknown", None)


def test_an_unreachable_dsp_creates_an_unvalidated_mapping(authenticated_client, line_id):
    _use_dsp_client(authenticated_client, ScriptedDspDeliveryClient(DspUnreachableError("down")))

    response = _post(authenticated_client, line_id)

    assert response.status_code == 201
    assert (response.json()["validation"], response.json()["validated_at"]) == ("unreachable", None)


def test_a_pair_already_mapped_is_a_conflict_with_a_code_and_a_message(authenticated_client, line_id):
    _use_dsp_client(authenticated_client, ScriptedDspDeliveryClient(KEY))
    _post(authenticated_client, line_id)

    response = _post(authenticated_client, line_id)

    assert response.status_code == 409
    assert set(response.json()) == {"code", "message"}
    assert response.json()["code"] == "duplicate_dsp_mapping"


def test_an_unknown_campaign_line_is_not_found(authenticated_client):
    _use_dsp_client(authenticated_client, ScriptedDspDeliveryClient(KEY))

    response = _post(authenticated_client, 0)

    assert (response.status_code, response.json()["code"]) == (404, "campaign_line_not_found")


def test_a_dsp_without_a_connector_is_unprocessable(authenticated_client, line_id):
    _use_dsp_client(authenticated_client, None)

    response = _post(authenticated_client, line_id)

    assert (response.status_code, response.json()["code"]) == (422, "dsp_not_supported")


def test_a_dsp_that_refuses_the_credentials_is_a_bad_gateway_without_detail(authenticated_client, line_id):
    _use_dsp_client(authenticated_client, ScriptedDspDeliveryClient(DspAuthenticationError("secret-detail")))

    response = _post(authenticated_client, line_id)

    assert (response.status_code, response.json()["code"]) == (502, "dsp_request_failed")
    assert "secret-detail" not in response.text


def test_no_error_body_carries_sql(authenticated_client, line_id):
    _use_dsp_client(authenticated_client, ScriptedDspDeliveryClient(KEY))
    _post(authenticated_client, line_id)

    body = _post(authenticated_client, line_id).text.lower()

    assert not any(word in body for word in ("insert", "constraint", "uq_dsp_mappings", "psycopg"))


def test_empty_identifiers_are_rejected_by_validation(authenticated_client, line_id):
    _use_dsp_client(authenticated_client, ScriptedDspDeliveryClient(KEY))

    response = _post(authenticated_client, line_id, {"external_campaign_id": "", "external_line_item_id": "2001"})

    assert response.status_code == 422


def test_a_user_without_the_operations_role_is_forbidden(authenticated_client_no_operations_role, test_db_session):
    line = insert_campaign_line(test_db_session)
    client = authenticated_client_no_operations_role
    _use_dsp_client(client, ScriptedDspDeliveryClient(KEY))

    response = _post(client, line)

    assert (response.status_code, response.json()["code"]) == (403, "missing_role")


def test_a_request_without_a_token_is_unauthenticated(client):
    response = _post(client, 1)

    assert (response.status_code, response.json()["code"]) == (401, "unauthenticated")


def _catalogue(session, impressions: date | None) -> None:
    SqlAlchemyDspCatalogRepository(session).upsert_all(seeded_dsp_id(session), [CatalogLineObservation(
        key=KEY, campaign_name="Synthetic Campaign", line_item_name="Synthetic Line",
        line_start_date=None, line_end_date=None, first_seen_date=date(2026, 8, 1), last_seen_date=date(2026, 8, 9),
        last_impressions_date=impressions,
    )])


def test_the_response_carries_the_last_impressions_date_when_the_pair_is_in_the_catalogue(
        authenticated_client, test_db_session, line_id):
    _catalogue(test_db_session, date(2026, 8, 7))
    _use_dsp_client(authenticated_client, ScriptedDspDeliveryClient(KEY))

    response = _post(authenticated_client, line_id)

    assert (response.status_code, response.json()["last_impressions_date"]) == (201, "2026-08-07")


def test_a_pair_in_the_catalogue_that_never_delivered_has_no_impressions_date(
        authenticated_client, test_db_session, line_id):
    _catalogue(test_db_session, None)
    _use_dsp_client(authenticated_client, ScriptedDspDeliveryClient(KEY))

    assert _post(authenticated_client, line_id).json()["last_impressions_date"] is None


def test_the_field_is_null_and_the_rest_of_the_contract_unchanged_when_the_pair_is_not_in_the_catalogue(
        authenticated_client, line_id):
    _use_dsp_client(authenticated_client, ScriptedDspDeliveryClient(KEY))

    body = _post(authenticated_client, line_id).json()

    assert body["last_impressions_date"] is None
    assert {"id", "campaign_line_id", "dsp_id", "external_campaign_id", "external_line_item_id", "validated_at",
            "validation"} <= set(body)


TODAY = date(2026, 8, 20)


def _line_starting(session, start: date) -> int:
    line = insert_campaign_line(session, line_start=start, line_end=date(2026, 8, 31))
    return line


@pytest.mark.parametrize(("start", "expected"), [(date(2026, 8, 12), True), (date(2026, 8, 13), False)])
def test_the_response_says_whether_the_line_needs_a_history_load_at_both_edges_of_the_window(
        authenticated_client, test_db_session, start, expected):
    authenticated_client.app.dependency_overrides[providers.get_today] = lambda: TODAY
    _use_dsp_client(authenticated_client, ScriptedDspDeliveryClient(KEY))

    response = _post(authenticated_client, _line_starting(test_db_session, start))

    assert (response.status_code, response.json()["needs_history_load"]) == (201, expected)


# --- An Equativ package written by operations ----------------------------------------------------------------------

PACKAGE = "900000001"
PACKAGE_BODY = {"external_campaign_id": PACKAGE, "external_line_item_id": PACKAGE}


def _equativ_line(session: Session) -> int:
    equativ = session.scalars(select(DSPRecord).where(DSPRecord.name == "Equativ")).first()
    if equativ is None:
        equativ = DSPRecord(name="Equativ", is_active=True)
        session.add(equativ)
        session.flush()
    return insert_campaign_line(session, campaign_name="Equativ endpoint", dsp_id=equativ.id)


def _no_client_may_be_asked(client: Any) -> None:
    def resolve(dsp_name: str) -> None:
        raise AssertionError(f"no client is asked for {dsp_name}")

    client.app.dependency_overrides[providers.get_dsp_client_resolver] = lambda: resolve


def test_an_equativ_package_is_mapped_validated_by_the_user(authenticated_client: Any, test_db_session: Session) -> None:
    line = _equativ_line(test_db_session)
    _no_client_may_be_asked(authenticated_client)

    response = _post(authenticated_client, line, PACKAGE_BODY)

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["validation"], body["campaign_line_id"]) == ("user_validated", line)
    assert (body["external_campaign_id"], body["external_line_item_id"]) == (PACKAGE, PACKAGE)
    assert body["validated_at"] is not None
    assert body["last_impressions_date"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"external_campaign_id": PACKAGE, "external_line_item_id": "900000002"},
        {"external_campaign_id": "abc", "external_line_item_id": "abc"},
        {"external_campaign_id": "9000-01", "external_line_item_id": "9000-01"},
        {"external_campaign_id": "0", "external_line_item_id": "0"},
        {"external_campaign_id": "0900000001", "external_line_item_id": "0900000001"},
    ],
    ids=["two-ids", "letters", "dash", "zero", "leading-zero"],
)
def test_a_malformed_equativ_pair_is_unprocessable_and_stores_nothing(
    authenticated_client: Any, test_db_session: Session, body: dict[str, str]
) -> None:
    line = _equativ_line(test_db_session)
    _no_client_may_be_asked(authenticated_client)

    response = _post(authenticated_client, line, body)

    assert response.status_code == 422
    assert response.json() == {
        "code": "invalid_equativ_package",
        "message": "An Equativ line is mapped by one auction package id, a whole number above zero with no leading zero, in both identifiers",
    }
    assert test_db_session.scalar(
        select(func.count()).select_from(DSPMappingRecord).where(DSPMappingRecord.campaign_line_id == line)
    ) == 0


def test_a_user_without_the_operations_role_cannot_map_an_equativ_line(
    authenticated_client_no_operations_role: Any, test_db_session: Session
) -> None:
    line = _equativ_line(test_db_session)
    _no_client_may_be_asked(authenticated_client_no_operations_role)

    response = _post(authenticated_client_no_operations_role, line, PACKAGE_BODY)

    assert (response.status_code, response.json()["code"]) == (403, "missing_role")


def test_a_request_without_a_token_cannot_map_an_equativ_line(client: Any, test_db_session: Session) -> None:
    line = _equativ_line(test_db_session)

    response = _post(client, line, PACKAGE_BODY)

    assert (response.status_code, response.json()["code"]) == (401, "unauthenticated")
