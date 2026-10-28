"""POST /margin/rebate-schedules and POST /margin/platform-rates: finance creates the rebate and rate data."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.infrastructure.persistence.models.campaign import CampaignLineRecord
from app.infrastructure.persistence.models.margin import PlatformRateSettingRecord, RebateBracketRecord, RebateScheduleRecord
from app.infrastructure.persistence.models.identity import UserRecord
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import insert_campaign_line
from tests.fixtures.margin_data import agency_of, group_of

TABLE = [{"lower": "0", "upper": "100000", "rate": "0.15"}, {"lower": "100000", "upper": None, "rate": "0.20"}]


@pytest.fixture
def world(client_for_roles, test_db_session):
    line_id = insert_campaign_line(test_db_session)
    line = test_db_session.get(CampaignLineRecord, line_id)
    client = client_for_roles("finance")
    client.app.dependency_overrides[providers.get_today] = lambda: date(2026, 9, 1)
    return client, {
        "line_id": line_id, "group_id": group_of(test_db_session, line_id), "agency_id": agency_of(test_db_session, line_id),
        "channel_id": line.channel_id,
    }


def _schedule(group_id: int, **overrides):
    body = {"holding_group_id": group_id, "valid_from": "2026-01-01", "brackets": TABLE}
    body.update(overrides)
    return body


def _schedules(session) -> int:
    return session.scalar(select(func.count()).select_from(RebateScheduleRecord))


# ---------------------------------------------------------------- schedules

def test_a_schedule_is_created_with_its_brackets(world, test_db_session):
    client, ids = world

    response = client.post("/margin/rebate-schedules", json=_schedule(ids["group_id"], channel_id=ids["channel_id"], scope="national"))

    assert response.status_code == 201
    body = response.json()
    assert body["holding_group_id"] == ids["group_id"] and body["scope"] == "national"
    assert [b["rate"] for b in body["brackets"]] == ["0.15", "0.20"]
    stored = test_db_session.get(RebateScheduleRecord, body["id"])
    assert (stored.valid_from, stored.valid_to, stored.agency_id) == (date(2026, 1, 1), None, None)
    assert [b.rate for b in test_db_session.scalars(select(RebateBracketRecord).order_by(RebateBracketRecord.position))] == [
        Decimal("0.15"), Decimal("0.20")]


def test_an_agency_exception_is_created(world, test_db_session):
    client, ids = world

    response = client.post("/margin/rebate-schedules", json=_schedule(ids["group_id"], agency_id=ids["agency_id"]))

    assert response.status_code == 201
    assert test_db_session.get(RebateScheduleRecord, response.json()["id"]).agency_id == ids["agency_id"]


@pytest.mark.parametrize(("table", "code"), [
    ([], "bracket_table_empty"),
    ([{"lower": "1000", "upper": None, "rate": "0.1"}], "bracket_table_must_start_at_zero"),
    ([{"lower": "0", "upper": "100", "rate": "0.1"}, {"lower": "120", "upper": None, "rate": "0.2"}], "bracket_table_not_contiguous"),
    ([{"lower": "0", "upper": "100", "rate": "0.1"}, {"lower": "100", "upper": "500", "rate": "0.2"}], "last_bracket_must_be_open"),
])
def test_an_invalid_table_is_refused_with_its_own_code_and_nothing_is_stored(world, test_db_session, table, code):
    client, ids = world

    response = client.post("/margin/rebate-schedules", json=_schedule(ids["group_id"], brackets=table))

    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}
    assert response.json()["code"] == code
    assert _schedules(test_db_session) == 0


def test_the_four_invalid_tables_read_differently(world):
    client, ids = world
    tables = [[], [{"lower": "1", "upper": None, "rate": "0.1"}],
              [{"lower": "0", "upper": "1", "rate": "0.1"}, {"lower": "2", "upper": None, "rate": "0.1"}],
              [{"lower": "0", "upper": "1", "rate": "0.1"}]]

    messages = [client.post("/margin/rebate-schedules", json=_schedule(ids["group_id"], brackets=t)).json()["message"] for t in tables]

    assert len(set(messages)) == 4


def test_an_overlapping_schedule_is_a_conflict_and_nothing_is_stored(world, test_db_session):
    client, ids = world
    client.post("/margin/rebate-schedules", json=_schedule(ids["group_id"], valid_to="2026-06-30"))

    response = client.post("/margin/rebate-schedules", json=_schedule(ids["group_id"], valid_from="2026-06-30"))

    assert response.status_code == 409
    assert response.json()["code"] == "schedule_overlaps_existing"
    assert set(response.json()) == {"code", "message"}
    assert _schedules(test_db_session) == 1


def test_back_to_back_validity_is_accepted(world):
    client, ids = world
    client.post("/margin/rebate-schedules", json=_schedule(ids["group_id"], valid_to="2026-06-30"))

    assert client.post("/margin/rebate-schedules", json=_schedule(ids["group_id"], valid_from="2026-07-01")).status_code == 201


def test_a_failed_creation_leaves_the_session_usable(world, test_db_session):
    client, ids = world
    client.post("/margin/rebate-schedules", json=_schedule(ids["group_id"]))
    client.post("/margin/rebate-schedules", json=_schedule(ids["group_id"]))  # conflict

    assert client.post("/margin/rebate-schedules", json=_schedule(ids["group_id"], channel_id=ids["channel_id"])).status_code == 201


@pytest.mark.parametrize("override", [{"holding_group_id": 987654}, {"agency_id": 987654}, {"channel_id": 987654}])
def test_a_reference_that_does_not_exist_is_unprocessable(world, test_db_session, override):
    client, ids = world

    response = client.post("/margin/rebate-schedules", json=_schedule(ids["group_id"], **override))

    assert response.status_code == 422
    assert response.json()["code"] == "reference_not_found"
    assert _schedules(test_db_session) == 0


def test_a_rate_posted_as_a_json_number_is_refused(world, test_db_session):
    client, ids = world
    table = [{"lower": "0", "upper": None, "rate": 0.15}]

    response = client.post("/margin/rebate-schedules", json=_schedule(ids["group_id"], brackets=table))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert _schedules(test_db_session) == 0


@pytest.mark.parametrize("override", [{"scope": "galaxy"}, {"valid_from": "soon"}, {"valid_to": "2025-01-01"}, {"holding_group_id": "x"}])
def test_an_invalid_schedule_body_is_code_and_message_only(world, test_db_session, override):
    client, ids = world

    response = client.post("/margin/rebate-schedules", json=_schedule(ids["group_id"], **override))

    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}
    assert _schedules(test_db_session) == 0


# ---------------------------------------------------------------- platform rates

def test_a_platform_rate_is_set_with_its_author_and_time(world, test_db_session):
    client, ids = world

    response = client.post("/margin/platform-rates", json={"level": "agency", "agency_id": ids["agency_id"], "rate_per_thousand": "1.40"})

    assert response.status_code == 201
    row = test_db_session.get(PlatformRateSettingRecord, response.json()["id"])
    author = test_db_session.scalars(select(UserRecord).where(UserRecord.email == "roles_finance@example.com")).one()
    assert (row.level, row.agency_id, row.rate_per_thousand, row.created_by) == ("agency", ids["agency_id"], Decimal("1.40"), author.id)
    assert row.created_at is not None
    assert response.json()["rate_per_thousand"] == "1.400000" and response.json()["created_by"] == author.id


def test_each_level_takes_its_own_key(world, test_db_session):
    client, ids = world
    posts = [
        {"level": "line", "campaign_line_id": ids["line_id"], "rate_per_thousand": "0.80"},
        {"level": "system", "rate_per_thousand": "1.10"},
    ]

    assert [client.post("/margin/platform-rates", json=body).status_code for body in posts] == [201, 201]


@pytest.mark.parametrize("body", [
    {"level": "agency", "rate_per_thousand": "1.4"},
    {"level": "line", "agency_id": 1, "rate_per_thousand": "1.4"},
    {"level": "system", "agency_id": 1, "rate_per_thousand": "1.4"},
    {"level": "galaxy", "rate_per_thousand": "1.4"},
    {"level": "system", "rate_per_thousand": "-1"},
    {"level": "system", "rate_per_thousand": 1.4},
    {"level": "system"},
])
def test_a_wrong_platform_rate_is_code_and_message_only_and_stores_nothing(world, test_db_session, body):
    client, _ = world
    before = test_db_session.scalar(select(func.count()).select_from(PlatformRateSettingRecord))

    response = client.post("/margin/platform-rates", json=body)

    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}
    assert test_db_session.scalar(select(func.count()).select_from(PlatformRateSettingRecord)) == before


def test_a_reference_to_something_missing_is_unprocessable(world):
    client, _ = world

    response = client.post("/margin/platform-rates", json={"level": "agency", "agency_id": 987654, "rate_per_thousand": "1.4"})

    assert response.status_code == 422
    assert response.json()["code"] == "reference_not_found"


def test_the_latest_setting_is_the_one_a_margin_read_uses(world, test_db_session):
    client, ids = world
    client.post("/margin/platform-rates", json={"level": "agency", "agency_id": ids["agency_id"], "rate_per_thousand": "1.00"})
    client.post("/margin/platform-rates", json={"level": "agency", "agency_id": ids["agency_id"], "rate_per_thousand": "3.00"})
    from tests.fixtures.delivery_data import insert_delivery, insert_ingestion_batch
    insert_delivery(test_db_session, ids["line_id"], date(2026, 8, 10), 1_000_000, insert_ingestion_batch(test_db_session))

    flight = client.get("/margin").json()["campaigns"][0]["lines"][0]["flights"][0]

    assert flight["platform_cost"] == "3000.00"
    assert flight["rates"]["platform_rate"] == "3.000000"


# ---------------------------------------------------------------- access

BODIES = [
    ("/margin/rebate-schedules", lambda ids: _schedule(ids["group_id"])),
    ("/margin/platform-rates", lambda ids: {"level": "system", "rate_per_thousand": "1.10"}),
]


@pytest.mark.parametrize(("path", "body"), BODIES)
@pytest.mark.parametrize("roles", [("operations",), ("business",), ("operations", "business"), ()])
def test_a_user_without_finance_is_forbidden_and_nothing_is_stored(client_for_roles, test_db_session, path, body, roles):
    line_id = insert_campaign_line(test_db_session)
    ids = {"group_id": group_of(test_db_session, line_id)}
    client = client_for_roles(*roles)
    before = (_schedules(test_db_session), test_db_session.scalar(select(func.count()).select_from(PlatformRateSettingRecord)))

    response = client.post(path, json=body(ids))

    assert response.status_code == 403
    assert set(response.json()) == {"code", "message"}
    assert (_schedules(test_db_session), test_db_session.scalar(select(func.count()).select_from(PlatformRateSettingRecord))) == before


@pytest.mark.parametrize(("path", "body"), BODIES)
def test_a_request_without_a_token_is_unauthenticated(client, path, body):
    response = client.post(path, json=body({"group_id": 1}))

    assert response.status_code == 401
    assert set(response.json()) == {"code", "message"}
