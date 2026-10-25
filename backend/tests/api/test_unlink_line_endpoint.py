"""DELETE /campaign-lines/{id}/dsp-mappings: the only mapping goes with the delivery it brought, in one transaction."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord
from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord
from app.infrastructure.persistence.repositories.sqlalchemy_line_mapping_removal_repository import (
    SqlAlchemyLineMappingRemovalRepository,
)
from tests.fixtures.delivery_data import (
    add_line_to_campaign,
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    insert_mapping,
    seeded_dsp_id,
)


@pytest.fixture
def line_id(test_db_session) -> int:
    created = insert_campaign_line(test_db_session, dsp_id=seeded_dsp_id(test_db_session))
    test_db_session.commit()  # a rollback by the request must not take the fixture with it
    return created


def _unlink(client, line_id: int):
    return client.delete(f"/campaign-lines/{line_id}/dsp-mappings")


def _count(session, record) -> int:
    return session.scalar(select(func.count()).select_from(record))


def _map_and_deliver(session, line_id: int, days: tuple[int, ...] = (3, 4, 5)) -> None:
    insert_mapping(session, line_id, seeded_dsp_id(session), "100", "200")
    batch_id = insert_ingestion_batch(session)
    for day in days:
        insert_delivery(session, line_id, date(2026, 8, day), 100, batch_id)
    session.commit()


def test_the_only_mapping_is_deleted_with_the_delivery_and_the_days_are_counted(authenticated_client, test_db_session, line_id):
    _map_and_deliver(test_db_session, line_id)

    response = _unlink(authenticated_client, line_id)

    assert response.status_code == 200, response.text
    assert response.json() == {"campaign_line_id": line_id, "removed_delivery_days": 3}
    assert (_count(test_db_session, DSPMappingRecord), _count(test_db_session, DailyDeliveryRecord)) == (0, 0)


def test_a_mapped_line_with_no_delivery_reports_zero_days(authenticated_client, test_db_session, line_id):
    _map_and_deliver(test_db_session, line_id, days=())

    response = _unlink(authenticated_client, line_id)

    assert (response.status_code, response.json()["removed_delivery_days"]) == (200, 0)
    assert _count(test_db_session, DSPMappingRecord) == 0


def test_only_the_delivery_of_that_line_goes(authenticated_client, test_db_session, line_id):
    _map_and_deliver(test_db_session, line_id, days=(3,))
    other = add_line_to_campaign(test_db_session, line_id, 2)
    insert_delivery(test_db_session, other, date(2026, 8, 3), 50, insert_ingestion_batch(test_db_session))
    insert_mapping(test_db_session, other, seeded_dsp_id(test_db_session), "100", "201")
    test_db_session.commit()

    _unlink(authenticated_client, line_id)

    remaining = test_db_session.scalars(select(DailyDeliveryRecord.campaign_line_id)).all()
    assert remaining == [other]
    assert _count(test_db_session, DSPMappingRecord) == 1


def test_several_mappings_are_ambiguous_and_nothing_is_deleted(authenticated_client, test_db_session, line_id):
    _map_and_deliver(test_db_session, line_id)
    insert_mapping(test_db_session, line_id, seeded_dsp_id(test_db_session), "100", "201")
    test_db_session.commit()

    response = _unlink(authenticated_client, line_id)

    assert (response.status_code, response.json()["code"]) == (409, "ambiguous_mapping")
    assert set(response.json()) == {"code", "message"}
    assert (_count(test_db_session, DSPMappingRecord), _count(test_db_session, DailyDeliveryRecord)) == (2, 3)


def test_a_line_without_a_mapping_is_not_found(authenticated_client, line_id):
    response = _unlink(authenticated_client, line_id)

    assert (response.status_code, response.json()["code"]) == (404, "mapping_not_found")
    assert set(response.json()) == {"code", "message"}


def test_an_unknown_line_is_not_found(authenticated_client):
    response = _unlink(authenticated_client, 0)

    assert (response.status_code, response.json()["code"]) == (404, "line_not_found")


def test_a_failure_while_deleting_the_delivery_keeps_the_mapping_and_the_delivery(
        authenticated_client, test_db_session, line_id, monkeypatch):
    _map_and_deliver(test_db_session, line_id)

    def explode(*_args, **_kwargs):
        raise RuntimeError("the database went away")

    monkeypatch.setattr(SqlAlchemyLineMappingRemovalRepository, "delete_deliveries", explode)
    client = TestClient(authenticated_client.app, raise_server_exceptions=False)

    response = _unlink(client, line_id)

    assert response.status_code == 500
    assert "database went away" not in response.text
    assert (_count(test_db_session, DSPMappingRecord), _count(test_db_session, DailyDeliveryRecord)) == (1, 3)


def test_unlinking_requires_the_operations_role(authenticated_client_no_operations_role):
    response = authenticated_client_no_operations_role.delete("/campaign-lines/1/dsp-mappings")

    assert response.status_code == 403
    assert set(response.json()) == {"code", "message"}
