"""A flight lies inside one calendar month, so it never crosses a year; a line mixes closed and running flights."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.services.flight_generation import generate_flights
from app.domain.services.flight_margin import calculate_flight_margin
from app.domain.services.margin_totals import total_flights
from app.domain.services.period_expansion import PeriodExpansionService
from app.domain.value_objects.flight import FlightWindow
from app.domain.value_objects.margin import FlightEconomics, FlightStatus


def _flights(line_start: date, line_end: date) -> list[FlightWindow]:
    campaign_periods = PeriodExpansionService().expand(line_start, line_end)
    return generate_flights(line_start, line_end, campaign_periods)


def _lies_inside_one_month(flight: FlightWindow) -> bool:
    return (flight.flight_start.year, flight.flight_start.month) == (flight.flight_end.year, flight.flight_end.month)


def test_a_line_over_a_year_end_has_one_flight_on_each_side():
    flights = _flights(date(2026, 12, 15), date(2027, 1, 20))

    assert [(flight.flight_start, flight.flight_end) for flight in flights] == [
        (date(2026, 12, 15), date(2026, 12, 31)),
        (date(2027, 1, 1), date(2027, 1, 20)),
    ]
    assert all(_lies_inside_one_month(flight) for flight in flights)


def test_a_flight_starting_on_the_last_day_of_the_year_ends_on_it():
    flights = _flights(date(2026, 12, 31), date(2027, 1, 31))

    assert flights[0] == FlightWindow(2026, 12, date(2026, 12, 31), date(2026, 12, 31))
    assert flights[0].flight_end.year == 2026


def test_a_flight_ending_on_the_first_day_of_the_year_starts_on_it():
    flights = _flights(date(2026, 12, 1), date(2027, 1, 1))

    assert flights[-1] == FlightWindow(2027, 1, date(2027, 1, 1), date(2027, 1, 1))
    assert flights[-1].flight_start.year == 2027


def test_a_line_from_the_last_day_to_the_first_day_has_two_one_day_flights():
    flights = _flights(date(2026, 12, 31), date(2027, 1, 1))

    assert [(flight.flight_start, flight.flight_end) for flight in flights] == [
        (date(2026, 12, 31), date(2026, 12, 31)),
        (date(2027, 1, 1), date(2027, 1, 1)),
    ]


@pytest.mark.parametrize("start_day", range(1, 32, 5))
@pytest.mark.parametrize("end_day", range(1, 32, 7))
def test_no_flight_ever_crosses_a_month_or_a_year(start_day: int, end_day: int):
    start = date(2026, 12, start_day)
    end = date(2027, 1, end_day)

    flights = _flights(start, end)

    assert flights
    assert all(_lies_inside_one_month(flight) for flight in flights)
    assert all(flight.flight_start.year == flight.flight_end.year for flight in flights)


def _economics(window: FlightWindow, contracted_impressions: int) -> FlightEconomics:
    return FlightEconomics(
        flight_start=window.flight_start,
        flight_end=window.flight_end,
        contracted_impressions=contracted_impressions,
        sale_cpm=Decimal("10.00"),
        delivered_impressions=0,
        media_cost=Decimal("0.00"),
        rebate_amount=Decimal("0"),
        platform_rate=Decimal("1.00"),
    )


def test_a_line_with_a_closed_flight_and_a_running_one_sums_both_and_is_provisional():
    august, september = _flights(date(2026, 8, 1), date(2026, 9, 30))
    as_of = date(2026, 9, 15)  # August has ended; September is 15 days in, of 30.
    margins = [
        calculate_flight_margin(_economics(august, 2000), as_of),     # closed: 20.00
        calculate_flight_margin(_economics(september, 4000), as_of),  # running: 40.00 x 15 / 30 = 20.00
    ]

    total = total_flights(margins)

    assert [margin.status for margin in margins] == [FlightStatus.CLOSED, FlightStatus.RUNNING]
    assert total.revenue == Decimal("40.00")
    assert total.provisional is True
    assert margins[0].provisional is False
