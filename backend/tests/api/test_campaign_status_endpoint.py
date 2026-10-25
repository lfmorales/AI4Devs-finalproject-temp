"""GET /campaign-status: running flights of active campaigns, flags, ordering, no cost, operations and business only."""

from datetime import date

import pytest

from app.presentation.dependencies import providers
from app.presentation.schemas.campaign_status import CampaignStatusResponse
from tests.fixtures.delivery_data import (
    CONTRACTED_IMPRESSIONS,
    add_line_to_campaign,
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    replace_flights,
)

TODAY = date(2026, 8, 11)  # D; D-1 is 10 August
COST_WORDS = ("cost", "cpm", "margin", "rebate", "revenue", "price")


@pytest.fixture
def business_client(client_for_roles):
    client = client_for_roles("business")
    client.app.dependency_overrides[providers.get_today] = lambda: TODAY
    return client


def _rows(client) -> list[dict]:
    response = client.get("/campaign-status")
    assert response.status_code == 200
    return response.json()


def _by_campaign(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["campaign"]["name"], []).append(row)
    return grouped


def test_a_running_flight_is_listed_with_every_figure(business_client, test_db_session):
    line = insert_campaign_line(test_db_session, campaign_name="Spring")
    insert_delivery(test_db_session, line, date(2026, 8, 10), 40_000, insert_ingestion_batch(test_db_session))

    [row] = _rows(business_client)

    assert row["campaign"]["name"] == "Spring" and row["agency"]["name"] == "Spring agency"
    assert row["line_number"] == 1
    assert row["flight"] == {
        "campaign_period_id": row["flight"]["campaign_period_id"], "year": 2026, "month": 8,
        "start": "2026-08-01", "end": "2026-08-31",
    }
    assert row["contracted_impressions"] == CONTRACTED_IMPRESSIONS
    assert row["delivered_impressions"] == 40_000
    assert row["delivery_ratio"] == pytest.approx(0.04)
    assert row["pacing"]["days_remaining"] == 21
    assert row["pacing"]["expected_impressions"] == pytest.approx(CONTRACTED_IMPRESSIONS * 10 / 31)
    assert row["pacing"]["deviation"] == pytest.approx(40_000 / (CONTRACTED_IMPRESSIONS * 10 / 31) - 1)


def test_contracted_and_delivered_are_distinct_and_delivered_counts_from_the_flight_start(business_client, test_db_session):
    line = insert_campaign_line(test_db_session)
    replace_flights(test_db_session, line, [(date(2026, 8, 5), date(2026, 8, 31))])
    batch = insert_ingestion_batch(test_db_session)
    insert_delivery(test_db_session, line, date(2026, 8, 4), 9_000, batch)
    insert_delivery(test_db_session, line, date(2026, 8, 5), 100, batch)

    [row] = _rows(business_client)

    assert (row["contracted_impressions"], row["delivered_impressions"]) == (CONTRACTED_IMPRESSIONS, 100)


def test_a_finished_flight_and_one_not_started_are_not_listed(business_client, test_db_session):
    line = insert_campaign_line(test_db_session)
    replace_flights(test_db_session, line, [(date(2026, 8, 1), date(2026, 8, 9)), (date(2026, 8, 11), date(2026, 8, 31))])

    assert _rows(business_client) == []


def test_a_campaign_that_is_not_active_is_not_listed(business_client, test_db_session):
    insert_campaign_line(test_db_session, status="paused")

    assert _rows(business_client) == []


def test_a_line_with_two_flights_lists_only_the_one_containing_d_minus_1(business_client, test_db_session):
    line = insert_campaign_line(test_db_session, end_date=date(2026, 9, 30))
    replace_flights(test_db_session, line, [(date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), date(2026, 9, 30))])

    [row] = _rows(business_client)

    assert row["flight"]["month"] == 8


def test_a_line_with_zero_impressions_in_a_running_flight_raises_the_pacing_flag(business_client, test_db_session):
    line = insert_campaign_line(test_db_session)
    insert_delivery(test_db_session, line, date(2026, 8, 10), 0, insert_ingestion_batch(test_db_session))

    [row] = _rows(business_client)

    assert row["delivered_impressions"] == 0
    assert row["pacing_flag"] is True
    assert row["pacing"]["status"] == "under_delivering"
    assert row["missing_data_flag"] is False  # a row of zeros is data received


def test_a_campaign_whose_latest_delivery_predates_d_minus_1_has_missing_data(business_client, test_db_session):
    line = insert_campaign_line(test_db_session)
    insert_delivery(test_db_session, line, date(2026, 8, 9), 500, insert_ingestion_batch(test_db_session))

    [row] = _rows(business_client)

    assert row["missing_data_flag"] is True


def test_a_campaign_with_no_delivery_at_all_has_missing_data(business_client, test_db_session):
    insert_campaign_line(test_db_session)

    [row] = _rows(business_client)

    assert row["missing_data_flag"] is True


def test_two_lines_of_a_campaign_repeat_the_same_missing_data_flag(business_client, test_db_session):
    first = insert_campaign_line(test_db_session)
    second = add_line_to_campaign(test_db_session, first, 2)
    # Only the second line delivers, on D-1: the campaign has data, so neither row is flagged.
    insert_delivery(test_db_session, second, date(2026, 8, 10), 5, insert_ingestion_batch(test_db_session))

    rows = _rows(business_client)

    assert [r["line_number"] for r in rows] == [1, 2]
    assert [r["missing_data_flag"] for r in rows] == [False, False]


def test_rows_with_a_flag_come_first_then_agency_campaign_and_line(business_client, test_db_session):
    batch = insert_ingestion_batch(test_db_session)
    ok_line = insert_campaign_line(test_db_session, campaign_name="A fine")
    insert_delivery(test_db_session, ok_line, date(2026, 8, 10), CONTRACTED_IMPRESSIONS * 10 // 31, batch)
    insert_campaign_line(test_db_session, campaign_name="Z stalled")

    names = [row["campaign"]["name"] for row in _rows(business_client)]

    assert names == ["Z stalled", "A fine"]


def test_no_field_of_the_response_is_a_cost_figure(business_client, test_db_session):
    line = insert_campaign_line(test_db_session)
    insert_delivery(test_db_session, line, date(2026, 8, 10), 40_000, insert_ingestion_batch(test_db_session))

    def names_in(value) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {n for v in value.values() for n in names_in(v)}
        if isinstance(value, list):
            return {n for v in value for n in names_in(v)}
        return set()

    def schema_names(model) -> set[str]:
        found: set[str] = set()
        for name, field in model.model_fields.items():
            found.add(name)
            annotation = field.annotation
            if hasattr(annotation, "model_fields"):
                found |= schema_names(annotation)
        return found

    returned = names_in(_rows(business_client))
    declared = schema_names(CampaignStatusResponse)

    assert returned and declared
    assert not [n for n in returned | declared if any(word in n.lower() for word in COST_WORDS)]


@pytest.mark.parametrize("roles", [("operations",), ("business",), ("operations", "business")])
def test_operations_and_business_may_read_the_status(client_for_roles, roles):
    client = client_for_roles(*roles)
    client.app.dependency_overrides[providers.get_today] = lambda: TODAY

    assert client.get("/campaign-status").status_code == 200


@pytest.mark.parametrize("roles", [("finance",), ()])
def test_a_user_with_neither_role_is_forbidden(client_for_roles, roles):
    response = client_for_roles(*roles).get("/campaign-status")

    assert response.status_code == 403
    assert set(response.json()) == {"code", "message"}


def test_a_request_without_a_token_is_unauthenticated(client):
    response = client.get("/campaign-status")

    assert response.status_code == 401
    assert set(response.json()) == {"code", "message"}
