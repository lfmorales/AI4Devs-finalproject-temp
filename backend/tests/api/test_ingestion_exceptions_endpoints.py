"""GET /ingestion-exceptions and POST /ingestion-exceptions/{id}/resolve: operations only, errors as code and message."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.value_objects.catalog import CatalogLineObservation
from app.domain.value_objects.delivery import ExternalLineKey, RetainedDelivery
from app.infrastructure.persistence.models.identity import UserRecord
from app.infrastructure.persistence.repositories.sqlalchemy_dsp_catalog_repository import (
    SqlAlchemyDspCatalogRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_ingestion_exception_repository import (
    SqlAlchemyIngestionExceptionRepository,
)
from tests.fixtures.delivery_data import insert_ingestion_batch, seeded_dsp_id

COST_MARKER = "98765.432101"


@pytest.fixture
def exception_id(test_db_session) -> int:
    repository = SqlAlchemyIngestionExceptionRepository(test_db_session)
    key = ExternalLineKey("9", "9")
    dsp_id = seeded_dsp_id(test_db_session)
    exception_id = repository.get_or_create_unmatched(dsp_id, key, insert_ingestion_batch(test_db_session))
    repository.add_retained(exception_id, [
        RetainedDelivery(key, date(2026, 8, 3), 100, 4, Decimal(COST_MARKER), 1, 1),
        RetainedDelivery(key, date(2026, 8, 5), 250, 6, Decimal("1.5"), 1, 1),
    ])
    repository.refresh_unmatched_date_spans(dsp_id)
    return exception_id


def _resolve(client, exception_id: int, body: dict | None = None):
    return client.post(f"/ingestion-exceptions/{exception_id}/resolve", json=body) if body is not None \
        else client.post(f"/ingestion-exceptions/{exception_id}/resolve")


def test_the_queue_shows_dates_days_and_totals(authenticated_client, exception_id):
    response = authenticated_client.get("/ingestion-exceptions")

    assert response.status_code == 200
    item = response.json()[0]
    assert (item["id"], item["exception_type"], item["status"]) == (exception_id, "unmatched_delivery", "open")
    assert (item["first_date"], item["last_date"], item["days"]) == ("2026-08-03", "2026-08-05", 2)
    assert (item["impressions_total"], item["clicks_total"]) == (350, 10)
    assert (item["external_campaign_id"], item["external_line_item_id"]) == ("9", "9")


def test_no_cost_reaches_the_response(authenticated_client, exception_id):
    text = authenticated_client.get("/ingestion-exceptions").text.lower()

    assert "cost" not in text and COST_MARKER not in text


def test_the_queue_filters_by_status(authenticated_client, exception_id):
    authenticated_client.post(f"/ingestion-exceptions/{exception_id}/resolve")

    open_items = authenticated_client.get("/ingestion-exceptions", params={"status": "open"}).json()
    resolved_items = authenticated_client.get("/ingestion-exceptions", params={"status": "resolved"}).json()

    assert (open_items, [i["id"] for i in resolved_items]) == ([], [exception_id])


def test_an_unknown_status_filter_is_rejected_by_validation(authenticated_client):
    assert authenticated_client.get("/ingestion-exceptions", params={"status": "pending"}).status_code == 422


def test_resolving_marks_the_exception_with_the_caller_and_the_note(authenticated_client, exception_id, test_db_session):
    response = _resolve(authenticated_client, exception_id, {"note": "Typo in the DSP name"})

    caller = test_db_session.query(UserRecord).filter_by(email="api_test@example.com").one()
    body = response.json()
    assert response.status_code == 200
    assert (body["status"], body["resolved_by"], body["note"]) == ("resolved", caller.id, "Typo in the DSP name")
    assert body["resolved_at"] is not None


def test_resolving_without_a_body_is_allowed(authenticated_client, exception_id):
    response = _resolve(authenticated_client, exception_id)

    assert (response.status_code, response.json()["note"]) == (200, None)


def test_a_resolved_exception_leaves_the_open_queue_and_stays_readable(authenticated_client, exception_id):
    _resolve(authenticated_client, exception_id)

    still_there = authenticated_client.get("/ingestion-exceptions", params={"status": "resolved"}).json()

    assert [(i["id"], i["days"], i["impressions_total"]) for i in still_there] == [(exception_id, 2, 350)]


def test_resolving_twice_is_a_conflict_with_a_code_and_a_message(authenticated_client, exception_id):
    _resolve(authenticated_client, exception_id)

    response = _resolve(authenticated_client, exception_id)

    assert (response.status_code, response.json()) == (
        409, {"code": "exception_already_resolved", "message": "The exception is already resolved"})


def test_resolving_an_unknown_exception_is_not_found(authenticated_client):
    response = _resolve(authenticated_client, 0)

    assert (response.status_code, response.json()["code"]) == (404, "exception_not_found")


def test_error_bodies_carry_no_sql(authenticated_client, exception_id):
    _resolve(authenticated_client, exception_id)

    body = _resolve(authenticated_client, exception_id).text.lower()

    assert not any(word in body for word in ("select", "update", "constraint", "psycopg"))


def test_a_user_without_operations_cannot_read_the_queue(authenticated_client_no_operations_role):
    response = authenticated_client_no_operations_role.get("/ingestion-exceptions")

    assert (response.status_code, response.json()["code"]) == (403, "missing_role")


def test_a_user_without_operations_cannot_resolve(authenticated_client_no_operations_role, exception_id):
    response = _resolve(authenticated_client_no_operations_role, exception_id)

    assert (response.status_code, response.json()["code"]) == (403, "missing_role")


def test_reading_the_queue_without_a_token_is_unauthenticated(client):
    response = client.get("/ingestion-exceptions")

    assert (response.status_code, response.json()["code"]) == (401, "unauthenticated")


def test_resolving_without_a_token_is_unauthenticated(client):
    response = client.post("/ingestion-exceptions/1/resolve")

    assert (response.status_code, response.json()["code"]) == (401, "unauthenticated")


def _catalogue_the_exception_pair(session) -> None:
    SqlAlchemyDspCatalogRepository(session).upsert_all(seeded_dsp_id(session), [CatalogLineObservation(
        key=ExternalLineKey("9", "9"), campaign_name="Synthetic Campaign", line_item_name="Synthetic Line",
        line_start_date=None, line_end_date=None, first_seen_date=date(2026, 8, 3), last_seen_date=date(2026, 8, 5),
        last_impressions_date=date(2026, 8, 5),
    )])


def test_the_queue_names_the_campaign_and_the_line_item_from_the_catalogue(authenticated_client, test_db_session, exception_id):
    _catalogue_the_exception_pair(test_db_session)

    item = authenticated_client.get("/ingestion-exceptions").json()[0]

    assert (item["campaign_name"], item["line_item_name"]) == ("Synthetic Campaign", "Synthetic Line")


def test_the_names_are_null_when_the_pair_is_not_in_the_catalogue(authenticated_client, exception_id):
    item = authenticated_client.get("/ingestion-exceptions").json()[0]

    assert (item["campaign_name"], item["line_item_name"]) == (None, None)


def test_a_resolved_exception_still_shows_its_names(authenticated_client, test_db_session, exception_id):
    _catalogue_the_exception_pair(test_db_session)

    resolved = authenticated_client.post(f"/ingestion-exceptions/{exception_id}/resolve").json()

    assert resolved["campaign_name"] == "Synthetic Campaign"


def test_names_do_not_bring_a_cost_into_the_queue(authenticated_client, test_db_session, exception_id):
    _catalogue_the_exception_pair(test_db_session)

    text = authenticated_client.get("/ingestion-exceptions").text.lower()

    assert "cost" not in text and COST_MARKER not in text


def test_a_missing_delivery_exception_has_no_names(authenticated_client, test_db_session):
    from tests.fixtures.delivery_data import insert_campaign_line, period_of_line

    line = insert_campaign_line(test_db_session)
    SqlAlchemyIngestionExceptionRepository(test_db_session).record_missing_delivery(
        line, period_of_line(test_db_session, line), insert_ingestion_batch(test_db_session))
    _catalogue_the_exception_pair(test_db_session)

    item = authenticated_client.get("/ingestion-exceptions").json()[0]

    assert (item["exception_type"], item["campaign_name"], item["line_item_name"]) == ("missing_delivery", None, None)
