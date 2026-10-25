"""The flight-level aggregate behind the daily status, against PostgreSQL: one query, delivery summed in the database."""

from datetime import date

from sqlalchemy import event

from app.infrastructure.persistence.repositories.sqlalchemy_campaign_status_repository import (
    SqlAlchemyCampaignStatusRepository,
)
from tests.fixtures.delivery_data import (
    CONTRACTED_IMPRESSIONS,
    add_line_to_campaign,
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    replace_flights,
)

D_MINUS_1 = date(2026, 8, 10)


def _running(session, as_of: date = D_MINUS_1):
    return SqlAlchemyCampaignStatusRepository(session).list_running_flights(as_of)


def test_a_running_flight_carries_its_campaign_agency_line_and_window(rolled_back_session):
    insert_campaign_line(rolled_back_session, campaign_name="Running")

    [figures] = _running(rolled_back_session)

    assert (figures.campaign_name, figures.agency_name) == ("Running", "Running agency")
    assert figures.line_number == 1
    assert (figures.flight_start, figures.flight_end) == (date(2026, 8, 1), date(2026, 8, 31))
    assert (figures.period_year, figures.period_month) == (2026, 8)
    assert figures.contracted_impressions == CONTRACTED_IMPRESSIONS


def test_a_flight_that_ended_and_one_that_has_not_started_are_not_returned(rolled_back_session):
    line = insert_campaign_line(rolled_back_session)
    replace_flights(rolled_back_session, line, [
        (date(2026, 8, 1), date(2026, 8, 9)),    # ended before D-1
        (date(2026, 8, 11), date(2026, 8, 31)),  # starts after D-1
    ])

    assert _running(rolled_back_session) == []


def test_the_boundaries_of_the_window_are_inclusive(rolled_back_session):
    line = insert_campaign_line(rolled_back_session)
    replace_flights(rolled_back_session, line, [(D_MINUS_1, D_MINUS_1)])

    assert len(_running(rolled_back_session)) == 1


def test_a_campaign_that_is_not_active_is_not_returned(rolled_back_session):
    insert_campaign_line(rolled_back_session, status="paused")

    assert _running(rolled_back_session) == []


def test_a_line_with_two_flights_returns_only_the_one_containing_d_minus_1(rolled_back_session):
    line = insert_campaign_line(rolled_back_session, end_date=date(2026, 9, 30))
    replace_flights(rolled_back_session, line, [
        (date(2026, 8, 1), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 9, 30)),
    ])

    [figures] = _running(rolled_back_session)

    assert figures.flight_start == date(2026, 8, 1)


def test_delivered_counts_only_from_the_flight_start_to_d_minus_1(rolled_back_session):
    line = insert_campaign_line(rolled_back_session)
    replace_flights(rolled_back_session, line, [(date(2026, 8, 5), date(2026, 8, 31))])
    batch = insert_ingestion_batch(rolled_back_session)
    insert_delivery(rolled_back_session, line, date(2026, 8, 4), 7_000, batch)   # before the flight
    insert_delivery(rolled_back_session, line, date(2026, 8, 5), 100, batch)
    insert_delivery(rolled_back_session, line, date(2026, 8, 10), 20, batch)
    insert_delivery(rolled_back_session, line, date(2026, 8, 11), 5_000, batch)  # after D-1

    [figures] = _running(rolled_back_session)

    assert figures.delivered_impressions == 120
    assert figures.contracted_impressions == CONTRACTED_IMPRESSIONS


def test_a_flight_with_no_delivery_has_zero_delivered_and_no_latest_date(rolled_back_session):
    insert_campaign_line(rolled_back_session)

    [figures] = _running(rolled_back_session)

    assert figures.delivered_impressions == 0
    assert figures.campaign_latest_delivery_date is None


def test_the_latest_delivery_date_is_the_campaigns_across_all_its_lines(rolled_back_session):
    first = insert_campaign_line(rolled_back_session)
    second = add_line_to_campaign(rolled_back_session, first, 2)
    batch = insert_ingestion_batch(rolled_back_session)
    insert_delivery(rolled_back_session, first, date(2026, 8, 8), 10, batch)
    insert_delivery(rolled_back_session, second, date(2026, 8, 10), 0, batch)

    rows = _running(rolled_back_session)

    assert [r.line_number for r in rows] == [1, 2]
    assert {r.campaign_latest_delivery_date for r in rows} == {date(2026, 8, 10)}
    assert [r.delivered_impressions for r in rows] == [10, 0]


def test_delivery_of_another_campaign_does_not_leak_into_a_row(rolled_back_session):
    insert_campaign_line(rolled_back_session, campaign_name="Mine")
    other = insert_campaign_line(rolled_back_session, campaign_name="Other")
    insert_delivery(rolled_back_session, other, date(2026, 8, 10), 999, insert_ingestion_batch(rolled_back_session))

    rows = {r.campaign_name: r for r in _running(rolled_back_session)}

    assert rows["Mine"].delivered_impressions == 0
    assert rows["Mine"].campaign_latest_delivery_date is None
    assert rows["Other"].delivered_impressions == 999


def test_the_aggregate_is_read_in_one_statement_whatever_the_number_of_rows(rolled_back_session):
    first = insert_campaign_line(rolled_back_session)
    add_line_to_campaign(rolled_back_session, first, 2)
    add_line_to_campaign(rolled_back_session, first, 3)
    insert_delivery(rolled_back_session, first, date(2026, 8, 10), 1, insert_ingestion_batch(rolled_back_session))
    statements: list[str] = []

    def record(conn, cursor, statement, *args):  # type: ignore[no-untyped-def]
        statements.append(statement)

    engine = rolled_back_session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        rows = _running(rolled_back_session)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert len(rows) == 3
    assert len(statements) == 1
