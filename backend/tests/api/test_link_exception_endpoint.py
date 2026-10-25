"""POST /ingestion-exceptions/{id}/link: a mapping and a resolution in one transaction, errors as code and message."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.domain.value_objects.delivery import ExternalLineKey, RetainedDelivery
from app.infrastructure.persistence.models.delivery import (
    DailyDeliveryRecord,
    IngestionExceptionDeliveryRecord,
    IngestionExceptionRecord,
)
from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord
from app.infrastructure.persistence.repositories.sqlalchemy_exception_link_repository import (
    SqlAlchemyExceptionLinkRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_ingestion_exception_repository import (
    SqlAlchemyIngestionExceptionRepository,
)
from tests.fixtures.delivery_data import (
    insert_campaign_line,
    insert_ingestion_batch,
    insert_mapping,
    insert_other_dsp,
    period_of_line,
    seeded_dsp_id,
)

KEY = ExternalLineKey("9", "9")


@pytest.fixture
def exception_id(test_db_session) -> int:
    repository = SqlAlchemyIngestionExceptionRepository(test_db_session)
    dsp_id = seeded_dsp_id(test_db_session)
    exception_id = repository.get_or_create_unmatched(dsp_id, KEY, insert_ingestion_batch(test_db_session))
    repository.add_retained(exception_id, [RetainedDelivery(KEY, date(2026, 8, 3), 100, 4, Decimal("1.5"), 1, 1)])
    repository.refresh_unmatched_date_spans(dsp_id)
    # Committed (to the test's outer transaction): a rollback by the request must not take the fixture with it.
    test_db_session.commit()
    return exception_id


@pytest.fixture
def line_id(test_db_session) -> int:
    created = insert_campaign_line(test_db_session, dsp_id=seeded_dsp_id(test_db_session))
    test_db_session.commit()
    return created


def _link(client, exception_id: int, line_id: int):
    return client.post(f"/ingestion-exceptions/{exception_id}/link", json={"campaign_line_id": line_id})


def _mappings(session) -> int:
    return session.scalar(select(func.count()).select_from(DSPMappingRecord))


def test_linking_creates_a_validated_mapping_and_resolves_the_exception(authenticated_client, test_db_session,
                                                                         exception_id, line_id):
    response = _link(authenticated_client, exception_id, line_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["mapping"]["campaign_line_id"], body["mapping"]["external_campaign_id"],
            body["mapping"]["external_line_item_id"]) == (line_id, "9", "9")
    assert body["mapping"]["validated_at"] is not None
    assert (body["exception"]["id"], body["exception"]["status"], body["exception"]["note"]) == (
        exception_id, "resolved", f"linked to line {line_id}")
    stored = test_db_session.scalars(select(DSPMappingRecord)).one()
    assert (stored.campaign_line_id, stored.validated_at is not None) == (line_id, True)


def test_the_retained_delivery_stays_on_the_exception_and_moves_nowhere(authenticated_client, test_db_session,
                                                                         exception_id, line_id):
    _link(authenticated_client, exception_id, line_id)

    assert test_db_session.scalar(select(func.count()).select_from(IngestionExceptionDeliveryRecord)) == 1
    assert test_db_session.scalar(select(func.count()).select_from(DailyDeliveryRecord)) == 0


def test_no_cost_reaches_the_response(authenticated_client, exception_id, line_id):
    assert "cost" not in _link(authenticated_client, exception_id, line_id).text.lower()


def test_an_unknown_exception_is_not_found(authenticated_client, line_id):
    response = _link(authenticated_client, 0, line_id)

    assert (response.status_code, response.json()["code"]) == (404, "exception_not_found")
    assert set(response.json()) == {"code", "message"}


def test_an_unknown_line_is_not_found_and_nothing_is_stored(authenticated_client, test_db_session, exception_id):
    response = _link(authenticated_client, exception_id, 0)

    assert (response.status_code, response.json()["code"]) == (404, "line_not_found")
    assert _mappings(test_db_session) == 0
    assert test_db_session.get(IngestionExceptionRecord, exception_id).status == "open"


def test_a_resolved_exception_is_a_conflict(authenticated_client, test_db_session, exception_id, line_id):
    authenticated_client.post(f"/ingestion-exceptions/{exception_id}/resolve")

    response = _link(authenticated_client, exception_id, line_id)

    assert (response.status_code, response.json()["code"]) == (409, "exception_already_resolved")
    assert _mappings(test_db_session) == 0


def test_a_pair_that_is_already_mapped_is_a_conflict_and_the_exception_stays_open(
        authenticated_client, test_db_session, exception_id, line_id):
    other_line = insert_campaign_line(test_db_session, campaign_name="Other", dsp_id=seeded_dsp_id(test_db_session))
    insert_mapping(test_db_session, other_line, seeded_dsp_id(test_db_session), "9", "9")
    test_db_session.commit()

    response = _link(authenticated_client, exception_id, line_id)

    assert (response.status_code, response.json()["code"]) == (409, "mapping_pair_taken")
    assert test_db_session.get(IngestionExceptionRecord, exception_id).status == "open"
    assert _mappings(test_db_session) == 1


def test_a_missing_delivery_exception_is_not_linkable(authenticated_client, test_db_session, line_id):
    missing = SqlAlchemyIngestionExceptionRepository(test_db_session)
    missing.record_missing_delivery(line_id, period_of_line(test_db_session, line_id), insert_ingestion_batch(test_db_session))
    missing_id = test_db_session.scalars(select(IngestionExceptionRecord.id)).one()

    response = _link(authenticated_client, missing_id, line_id)

    assert (response.status_code, response.json()["code"]) == (409, "exception_not_linkable")
    assert _mappings(test_db_session) == 0


def test_a_line_of_another_dsp_is_unprocessable(authenticated_client, test_db_session, exception_id):
    foreign_line = insert_campaign_line(test_db_session, campaign_name="Foreign", dsp_id=insert_other_dsp(test_db_session))

    response = _link(authenticated_client, exception_id, foreign_line)

    assert (response.status_code, response.json()["code"]) == (422, "line_dsp_mismatch")
    assert _mappings(test_db_session) == 0


def test_the_body_must_name_a_line(authenticated_client, exception_id):
    assert authenticated_client.post(f"/ingestion-exceptions/{exception_id}/link", json={}).status_code == 422


def test_a_failure_while_resolving_leaves_neither_a_mapping_nor_a_resolution(
        authenticated_client, test_db_session, exception_id, line_id, monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("the database went away")

    monkeypatch.setattr(SqlAlchemyExceptionLinkRepository, "resolve", explode)
    client = TestClient(authenticated_client.app, raise_server_exceptions=False)

    response = _link(client, exception_id, line_id)

    assert response.status_code == 500
    assert set(response.json()) == {"code", "message"}
    assert "database went away" not in response.text
    test_db_session.expire_all()
    assert _mappings(test_db_session) == 0
    assert test_db_session.get(IngestionExceptionRecord, exception_id).status == "open"


def test_linking_requires_the_operations_role(authenticated_client_no_operations_role):
    response = authenticated_client_no_operations_role.post("/ingestion-exceptions/1/link", json={"campaign_line_id": 1})

    assert response.status_code == 403
    assert set(response.json()) == {"code", "message"}
