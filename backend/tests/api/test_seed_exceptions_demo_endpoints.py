"""The demonstration data of the exception queue works through the real endpoints: the queue and the linking."""

from datetime import date

import pytest
from sqlalchemy import func, select

from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord
from app.presentation.dependencies import providers
from scripts.seed_exceptions_demo import ABSENCE_NAME, CAMPAIGN_NAME, main
from tests.fixtures.delivery_data import insert_user
from app.infrastructure.persistence.models.campaign import CampaignLineRecord, CampaignRecord

TODAY = date(2026, 10, 28)
DEVELOPER = "developer@example.com"


@pytest.fixture
def operations(client_for_roles, test_db_session):
    insert_user(test_db_session, DEVELOPER)
    test_db_session.commit()
    assert main([], out=lambda line: None, session_factory=lambda: test_db_session, today=TODAY, developer_email=DEVELOPER) == 0
    client = client_for_roles("operations")
    client.app.dependency_overrides[providers.get_today] = lambda: TODAY
    return client


def _line_id(session, campaign_name: str) -> int:
    return session.scalars(
        select(CampaignLineRecord.id).join(CampaignRecord, CampaignRecord.id == CampaignLineRecord.campaign_id)
        .where(CampaignRecord.name == campaign_name)
    ).one()


def _queue(client) -> list[dict]:
    response = client.get("/ingestion-exceptions")
    assert response.status_code == 200
    return response.json()


def test_the_queue_lists_three_open_one_resolved_and_one_missing_delivery_with_their_status(operations):
    items = _queue(operations)

    summary = sorted((item["exception_type"], item["status"]) for item in items)

    assert summary == [
        ("missing_delivery", "open"),
        ("unmatched_delivery", "open"),
        ("unmatched_delivery", "open"),
        ("unmatched_delivery", "open"),
        ("unmatched_delivery", "resolved"),
    ]


def test_the_status_filter_separates_the_resolved_tab_from_the_open_one(operations):
    resolved = operations.get("/ingestion-exceptions", params={"status": "resolved"}).json()
    opened = operations.get("/ingestion-exceptions", params={"status": "open"}).json()

    assert len(resolved) == 1 and resolved[0]["note"]
    assert len(opened) == 4


def test_the_open_unmatched_exceptions_carry_their_catalogue_names_and_their_retained_days(operations):
    unmatched = [i for i in _queue(operations) if i["exception_type"] == "unmatched_delivery" and i["status"] == "open"]

    assert all(i["line_item_name"].startswith("DEMO Cat") and i["days"] >= 3 and i["impressions_total"] > 0 for i in unmatched)


def test_the_missing_delivery_points_at_the_mapped_line_of_the_absence_campaign(operations, test_db_session):
    missing = next(i for i in _queue(operations) if i["exception_type"] == "missing_delivery")

    assert missing["campaign_line_id"] == _line_id(test_db_session, ABSENCE_NAME)


def test_the_queue_shows_no_cost(operations):
    assert "cost" not in operations.get("/ingestion-exceptions").text.lower()


def test_linking_an_open_exception_creates_the_mapping_resolves_it_and_asks_for_the_history(operations, test_db_session):
    target = next(i for i in _queue(operations) if i["exception_type"] == "unmatched_delivery" and i["status"] == "open")
    line_id = _line_id(test_db_session, CAMPAIGN_NAME)
    mappings_before = test_db_session.scalar(select(func.count()).select_from(DSPMappingRecord))

    response = operations.post(f"/ingestion-exceptions/{target['id']}/link", json={"campaign_line_id": line_id})

    body = response.json()
    assert response.status_code == 200
    assert body["needs_history_load"] is True
    assert body["exception"]["status"] == "resolved"
    assert body["mapping"]["campaign_line_id"] == line_id
    assert (body["mapping"]["external_campaign_id"], body["mapping"]["external_line_item_id"]) == (
        target["external_campaign_id"], target["external_line_item_id"])
    assert test_db_session.scalar(select(func.count()).select_from(DSPMappingRecord)) == mappings_before + 1
    still_open = [i for i in _queue(operations) if i["exception_type"] == "unmatched_delivery" and i["status"] == "open"]
    assert target["id"] not in {i["id"] for i in still_open} and len(still_open) == 2


def test_a_second_seeding_after_a_link_does_not_reopen_the_linked_exception(operations, test_db_session):
    target = next(i for i in _queue(operations) if i["exception_type"] == "unmatched_delivery" and i["status"] == "open")
    operations.post(f"/ingestion-exceptions/{target['id']}/link", json={"campaign_line_id": _line_id(test_db_session, CAMPAIGN_NAME)})

    assert main([], out=lambda line: None, session_factory=lambda: test_db_session, today=TODAY, developer_email=DEVELOPER) == 0

    again = next(i for i in _queue(operations) if i["id"] == target["id"])
    assert again["status"] == "resolved"
