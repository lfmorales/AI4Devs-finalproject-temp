"""GET /margin: campaigns, lines and flights with totals; closed, pending close, running; finance only."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.domain.services.flight_margin import round_amount
from app.infrastructure.persistence.models.margin import (
    AppliedRateBracketRecord,
    AppliedRateRecord,
    PlatformRateSettingRecord,
    RebateBracketRecord,
    RebateScheduleRecord,
)
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import (
    add_line_to_campaign,
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    replace_flights,
)
from tests.fixtures.margin_data import add_schedule, group_of, set_volume

SEPTEMBER_FIRST = date(2026, 9, 1)  # as_of is 31 August: August is over
AUGUST_11 = date(2026, 8, 11)       # as_of is 10 August: August is running
AMOUNTS = ("revenue", "media_cost", "rebate", "platform_cost", "margin")


def _client(client_for_roles, today: date, roles: tuple[str, ...] = ("finance",)):
    client = client_for_roles(*roles)
    client.app.dependency_overrides[providers.get_today] = lambda: today
    return client


def _get(client, **params):
    response = client.get("/margin", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _flights(body) -> list[dict]:
    return [f for c in body["campaigns"] for l in c["lines"] for f in l["flights"]]


def _count_rows(session) -> dict[str, int]:
    return {
        model.__tablename__: session.scalar(select(func.count()).select_from(model))
        for model in (AppliedRateRecord, AppliedRateBracketRecord, PlatformRateSettingRecord, RebateScheduleRecord, RebateBracketRecord)
    }


def _walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def test_a_flight_that_ended_and_is_not_closed_is_pending_close_and_provisional(client_for_roles, test_db_session):
    insert_campaign_line(test_db_session)

    body = _get(_client(client_for_roles, SEPTEMBER_FIRST))
    (flight,) = _flights(body)

    assert flight["state"] == "pending_close"
    assert flight["provisional"] is True
    assert flight["revenue"] == "5000.00"
    assert body["as_of"] == "2026-08-31"


def test_a_closed_flight_is_read_from_what_was_frozen_and_is_not_provisional(client_for_roles, test_db_session):
    line_id = insert_campaign_line(test_db_session)
    add_schedule(test_db_session, group_of(test_db_session, line_id), ("0", None, "0.25"))
    client = _client(client_for_roles, SEPTEMBER_FIRST)
    assert client.post("/margin/closings", json={"year": 2026, "month": 8}).status_code == 200

    (flight,) = _flights(_get(client))

    assert flight["state"] == "closed"
    assert flight["provisional"] is False
    assert flight["rebate"] == "1250.00"
    assert flight["rates"]["rebate_step"] == 6 and flight["rates"]["platform_rate"] == "1.000000"


def test_a_running_flight_is_calculated_pro_rated_and_provisional(client_for_roles, test_db_session):
    insert_campaign_line(test_db_session)

    (flight,) = _flights(_get(_client(client_for_roles, AUGUST_11)))

    assert flight["state"] == "running"
    assert flight["provisional"] is True
    assert Decimal(flight["revenue"]) == round_amount(Decimal("5000") * 10 / 31)


def test_a_flight_that_has_not_started_does_not_appear(client_for_roles, test_db_session):
    line_id = insert_campaign_line(test_db_session, start_date=date(2026, 8, 1), end_date=date(2026, 10, 31))
    replace_flights(test_db_session, line_id, [(date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 10, 1), date(2026, 10, 31))])

    flights = _flights(_get(_client(client_for_roles, SEPTEMBER_FIRST)))

    assert [f["flight_start"] for f in flights] == ["2026-08-01"]


def test_a_line_with_a_closed_flight_and_a_running_one_shows_both_and_is_provisional(client_for_roles, test_db_session):
    line_id = insert_campaign_line(test_db_session, start_date=date(2026, 8, 1), end_date=date(2026, 9, 30))
    replace_flights(test_db_session, line_id, [(date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), date(2026, 9, 30))])
    client = _client(client_for_roles, SEPTEMBER_FIRST)
    client.post("/margin/closings", json={"year": 2026, "month": 8})
    client.app.dependency_overrides[providers.get_today] = lambda: date(2026, 9, 11)

    body = _get(client)
    (line,) = body["campaigns"][0]["lines"]

    assert [f["state"] for f in line["flights"]] == ["closed", "running"]
    assert line["totals"]["provisional"] is True
    assert Decimal(line["totals"]["revenue"]) == sum(Decimal(f["revenue"]) for f in line["flights"])
    assert body["campaigns"][0]["totals"]["provisional"] is True and body["totals"]["provisional"] is True


def test_totals_are_the_sum_of_their_detail_at_every_level(client_for_roles, test_db_session):
    first = insert_campaign_line(test_db_session)
    add_line_to_campaign(test_db_session, first, 2)
    insert_campaign_line(test_db_session, campaign_name="Second campaign")

    body = _get(_client(client_for_roles, SEPTEMBER_FIRST))

    for campaign in body["campaigns"]:
        for line in campaign["lines"]:
            for amount in AMOUNTS:
                assert Decimal(line["totals"][amount]) == sum(Decimal(f[amount]) for f in line["flights"])
        for amount in AMOUNTS:
            assert Decimal(campaign["totals"][amount]) == sum(Decimal(l["totals"][amount]) for l in campaign["lines"])
    for amount in AMOUNTS:
        assert Decimal(body["totals"][amount]) == sum(Decimal(c["totals"][amount]) for c in body["campaigns"])
    assert len(body["campaigns"]) == 2


def test_filters_by_year_month_and_campaign(client_for_roles, test_db_session):
    first = insert_campaign_line(test_db_session, campaign_name="Alpha")
    second = insert_campaign_line(test_db_session, campaign_name="Beta", start_date=date(2026, 7, 1), end_date=date(2026, 7, 31))
    replace_flights(test_db_session, second, [(date(2026, 7, 1), date(2026, 7, 31))])
    client = _client(client_for_roles, SEPTEMBER_FIRST)
    campaign_ids = {c["name"]: c["campaign_id"] for c in _get(client)["campaigns"]}

    assert {f["period_month"] for f in _flights(_get(client, month=7))} == {7}
    assert _flights(_get(client, year=2025)) == []
    assert len(_flights(_get(client, year=2026, month=8))) == 1
    only_beta = _get(client, campaign_id=campaign_ids["Beta"])
    assert [c["name"] for c in only_beta["campaigns"]] == ["Beta"]
    assert first != second


def test_an_unknown_campaign_is_not_found(client_for_roles, test_db_session):
    response = _client(client_for_roles, SEPTEMBER_FIRST).get("/margin", params={"campaign_id": 999999})

    assert response.status_code == 404
    assert response.json()["code"] == "campaign_not_found"
    assert set(response.json()) == {"code", "message"}


def test_inactive_campaigns_are_included(client_for_roles, test_db_session):
    insert_campaign_line(test_db_session, status="inactive")

    body = _get(_client(client_for_roles, SEPTEMBER_FIRST))

    assert [c["status"] for c in body["campaigns"]] == ["inactive"]


def test_every_amount_is_a_decimal_string_and_no_float_appears_anywhere(client_for_roles, test_db_session):
    first = insert_campaign_line(test_db_session)
    add_schedule(test_db_session, group_of(test_db_session, first), ("0", "1000", "0.15"), ("1000", None, "0.2"))
    client = _client(client_for_roles, SEPTEMBER_FIRST)
    client.post("/margin/closings", json={"year": 2026, "month": 8})

    body = _get(client)

    assert not [value for value in _walk(body) if isinstance(value, float)]
    for flight in _flights(body):
        assert all(isinstance(flight[amount], str) for amount in AMOUNTS)
    for totals in (body["totals"], body["campaigns"][0]["totals"]):
        assert all(isinstance(totals[amount], str) for amount in AMOUNTS)
    assert Decimal(_flights(body)[0]["rates"]["effective_rebate_rate"]) > 0


def test_below_cost_flights_are_counted_at_every_level_without_changing_totals(client_for_roles, test_db_session):
    first = insert_campaign_line(test_db_session)
    second = add_line_to_campaign(test_db_session, first, 2)
    batch = insert_ingestion_batch(test_db_session)
    insert_delivery(test_db_session, second, date(2026, 8, 10), 1000, batch, Decimal("9000.00"))  # costs more than 5,000

    body = _get(_client(client_for_roles, SEPTEMBER_FIRST))
    lines = body["campaigns"][0]["lines"]

    assert [line["totals"]["below_cost_count"] for line in lines] == [0, 1]
    assert [f["below_cost"] for f in _flights(body)] == [False, True]
    assert body["campaigns"][0]["totals"]["below_cost_count"] == 1 and body["totals"]["below_cost_count"] == 1
    assert Decimal(body["totals"]["margin"]) == sum(Decimal(f["margin"]) for f in _flights(body))
    assert Decimal(lines[1]["totals"]["margin"]) < 0


def test_reading_writes_nothing(client_for_roles, test_db_session):
    line_id = insert_campaign_line(test_db_session)
    add_schedule(test_db_session, group_of(test_db_session, line_id), ("0", None, "0.25"))
    client = _client(client_for_roles, SEPTEMBER_FIRST)
    before = _count_rows(test_db_session)

    _get(client)
    _get(client, year=2026, month=8)

    assert _count_rows(test_db_session) == before
    assert before["applied_rates"] == 0
    assert not test_db_session.new and not test_db_session.dirty


def test_an_invalid_filter_is_code_and_message_only(client_for_roles, test_db_session):
    response = _client(client_for_roles, SEPTEMBER_FIRST).get("/margin", params={"month": 13})

    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize("roles", [("operations",), ("business",), ("operations", "business"), ()])
def test_a_user_without_finance_gets_403_and_no_margin_field(client_for_roles, test_db_session, roles):
    insert_campaign_line(test_db_session)

    response = _client(client_for_roles, SEPTEMBER_FIRST, roles).get("/margin")

    assert response.status_code == 403
    assert set(response.json()) == {"code", "message"}
    assert not any(word in response.text.lower() for word in ("revenue", "rebate", "margin", "cost"))


def test_a_request_without_a_token_is_unauthenticated(client):
    response = client.get("/margin")

    assert response.status_code == 401
    assert set(response.json()) == {"code", "message"}


def test_a_user_holding_finance_among_other_roles_reads_the_margin(client_for_roles, test_db_session):
    insert_campaign_line(test_db_session)

    assert _client(client_for_roles, SEPTEMBER_FIRST, ("operations", "finance")).get("/margin").status_code == 200


def test_delivery_is_aggregated_in_the_database_and_no_delivery_row_reaches_the_application(client_for_roles, test_db_session):
    from sqlalchemy import event

    line_id = insert_campaign_line(test_db_session)
    batch = insert_ingestion_batch(test_db_session)
    for day in range(1, 11):
        insert_delivery(test_db_session, line_id, date(2026, 8, day), 100, batch, Decimal("1.00"))
    client = _client(client_for_roles, SEPTEMBER_FIRST)
    statements: list[str] = []
    bind = test_db_session.get_bind()

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.split()).lower())

    event.listen(bind, "before_cursor_execute", record)
    try:
        body = _get(client)
    finally:
        event.remove(bind, "before_cursor_execute", record)

    touching_delivery = [s for s in statements if "daily_deliveries" in s]
    assert touching_delivery, "the margin read should aggregate delivery"
    assert all("sum(daily_deliveries." in s for s in touching_delivery)
    assert not any(s.startswith("select daily_deliveries.") for s in touching_delivery)
    assert _flights(body)[0]["media_cost"] == "10.00"
