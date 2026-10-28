"""contracted_revenue (the sale of the whole flight) and the accrued/window days next to the accrued revenue."""

from datetime import date
from decimal import Decimal

from app.domain.services.flight_margin import calculate_flight_margin
from app.domain.services.margin_totals import total_flights, total_lines
from app.domain.value_objects.margin import FlightEconomics, FlightStatus

AS_OF = date(2026, 8, 10)


def _flight(start: date = date(2026, 8, 1), end: date = date(2026, 8, 31), contracted: int = 1_000_000, cpm: str = "5.00"):
    return calculate_flight_margin(
        FlightEconomics(
            flight_start=start, flight_end=end, contracted_impressions=contracted, sale_cpm=Decimal(cpm),
            delivered_impressions=0, media_cost=Decimal("0"), rebate_amount=Decimal("0"), platform_rate=Decimal("1.00"),
        ),
        AS_OF,
    )


def test_a_running_flight_has_the_whole_sale_and_fewer_accrued_days_than_window_days():
    result = _flight()

    assert result.status is FlightStatus.RUNNING
    assert result.contracted_revenue == Decimal("5000.00")
    assert result.revenue == Decimal("1612.90")  # 5000 x 10 / 31
    assert (result.accrued_days, result.window_days) == (10, 31)
    assert result.accrued_days < result.window_days


def test_a_closed_flight_accrues_all_of_it():
    result = _flight(end=date(2026, 8, 10))

    assert result.status is FlightStatus.CLOSED
    assert result.revenue == result.contracted_revenue == Decimal("5000.00")
    assert (result.accrued_days, result.window_days) == (10, 10)


def test_a_flight_that_has_not_started_has_none_of_them():
    result = _flight(start=date(2026, 8, 11))

    assert result.status is FlightStatus.NOT_STARTED
    assert (result.contracted_revenue, result.accrued_days, result.window_days) == (None, None, None)


def test_a_line_without_a_price_has_a_contracted_revenue_of_zero():
    result = _flight(cpm="0.00")

    assert result.contracted_revenue == Decimal("0.00") and str(result.contracted_revenue) == "0.00"


def test_the_contracted_revenue_is_rounded_half_up_once_like_the_revenue():
    assert _flight(end=date(2026, 8, 10), contracted=25, cpm="5.00").contracted_revenue == Decimal("0.13")  # 0.125
    assert _flight(end=date(2026, 8, 10), contracted=2_001, cpm="5.00").contracted_revenue == Decimal("10.01")  # 10.005


def test_a_line_and_a_campaign_add_the_contracted_revenue_of_their_flights_without_rounding_again():
    flights = [_flight(end=date(2026, 8, 10), contracted=2_000, cpm="5.002") for _ in range(3)]  # 10.004 each

    line = total_flights(flights)

    assert [f.contracted_revenue for f in flights] == [Decimal("10.00")] * 3
    assert line.contracted_revenue == Decimal("30.00")
    assert total_lines([line, line]).contracted_revenue == Decimal("60.00")


def test_a_flight_not_started_adds_nothing_to_the_contracted_revenue_of_a_line():
    line = total_flights([_flight(end=date(2026, 8, 10)), _flight(start=date(2026, 8, 11))])

    assert line.contracted_revenue == Decimal("5000.00") and line.not_started_count == 1


def test_a_running_flight_does_not_change_the_existing_amounts():
    result = _flight()

    assert (result.revenue, result.provisional) == (Decimal("1612.90"), True)
