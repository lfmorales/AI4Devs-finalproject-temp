from datetime import date

import pytest

from app.domain.services.flight_generation import generate_flights
from app.domain.services.period_expansion import PeriodExpansionService
from app.domain.value_objects.flight import FlightWindow

CAMPAIGN_START = date(2026, 8, 1)
CAMPAIGN_END = date(2026, 12, 31)


def _periods(start: date = CAMPAIGN_START, end: date = CAMPAIGN_END):
    return PeriodExpansionService().expand(start, end)


def test_a_line_over_the_whole_campaign_has_one_flight_per_month():
    flights = generate_flights(CAMPAIGN_START, CAMPAIGN_END, _periods())

    assert [(flight.period_year, flight.period_month) for flight in flights] == [
        (2026, 8), (2026, 9), (2026, 10), (2026, 11), (2026, 12),
    ]
    assert flights[0] == FlightWindow(2026, 8, date(2026, 8, 1), date(2026, 8, 31))
    assert flights[-1] == FlightWindow(2026, 12, date(2026, 12, 1), date(2026, 12, 31))


def test_a_line_starting_mid_month_is_clipped_in_its_first_flight():
    flights = generate_flights(date(2026, 8, 15), CAMPAIGN_END, _periods())

    assert flights[0] == FlightWindow(2026, 8, date(2026, 8, 15), date(2026, 8, 31))
    assert flights[1] == FlightWindow(2026, 9, date(2026, 9, 1), date(2026, 9, 30))
    assert len(flights) == 5


def test_a_line_ending_before_the_campaign_has_no_flight_afterwards():
    flights = generate_flights(CAMPAIGN_START, date(2026, 9, 20), _periods())

    assert flights == [
        FlightWindow(2026, 8, date(2026, 8, 1), date(2026, 8, 31)),
        FlightWindow(2026, 9, date(2026, 9, 1), date(2026, 9, 20)),
    ]


def test_a_line_inside_one_month_has_a_single_flight():
    flights = generate_flights(date(2026, 10, 5), date(2026, 10, 25), _periods())

    assert flights == [FlightWindow(2026, 10, date(2026, 10, 5), date(2026, 10, 25))]


def test_a_line_of_a_single_day_has_a_single_flight_of_one_day():
    flights = generate_flights(date(2026, 11, 30), date(2026, 11, 30), _periods())

    assert flights == [FlightWindow(2026, 11, date(2026, 11, 30), date(2026, 11, 30))]
    assert flights[0].days == 1


def test_a_line_that_ends_on_the_first_day_of_a_month_gets_a_flight_of_one_day_in_it():
    flights = generate_flights(date(2026, 9, 20), date(2026, 10, 1), _periods())

    assert flights == [
        FlightWindow(2026, 9, date(2026, 9, 20), date(2026, 9, 30)),
        FlightWindow(2026, 10, date(2026, 10, 1), date(2026, 10, 1)),
    ]


def test_months_the_line_does_not_reach_get_no_flight():
    flights = generate_flights(date(2026, 10, 1), date(2026, 10, 31), _periods())

    assert [(flight.period_year, flight.period_month) for flight in flights] == [(2026, 10)]


def test_a_campaign_clipped_period_clips_the_flight_too():
    periods = _periods(date(2026, 8, 15), date(2026, 9, 10))

    flights = generate_flights(date(2026, 8, 15), date(2026, 9, 10), periods)

    assert flights == [
        FlightWindow(2026, 8, date(2026, 8, 15), date(2026, 8, 31)),
        FlightWindow(2026, 9, date(2026, 9, 1), date(2026, 9, 10)),
    ]


def test_flights_follow_the_year_change():
    periods = _periods(date(2026, 12, 10), date(2027, 1, 20))

    flights = generate_flights(date(2026, 12, 10), date(2027, 1, 20), periods)

    assert [(flight.period_year, flight.period_month) for flight in flights] == [(2026, 12), (2027, 1)]


def test_a_line_ending_before_it_starts_is_refused():
    with pytest.raises(ValueError):
        generate_flights(date(2026, 9, 2), date(2026, 9, 1), _periods())
