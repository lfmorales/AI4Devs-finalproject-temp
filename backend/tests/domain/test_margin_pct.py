"""margin_pct: margin over revenue in percentage points, two decimals, half up, null when revenue is zero."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.services.flight_margin import calculate_flight_margin
from app.domain.services.margin_totals import total_flights, total_lines
from app.domain.value_objects.margin import FlightEconomics, margin_percentage

AS_OF = date(2026, 9, 5)


def _flight(contracted_impressions: int = 726_202, sale_cpm: str = "5.00", media_cost: str = "1200.00",
            rebate_amount: str = "907.7525", delivered: int = 700_000, start=date(2026, 8, 1), end=date(2026, 8, 31)):
    return calculate_flight_margin(
        FlightEconomics(
            flight_start=start, flight_end=end, contracted_impressions=contracted_impressions,
            sale_cpm=Decimal(sale_cpm), delivered_impressions=delivered, media_cost=Decimal(media_cost),
            rebate_amount=Decimal(rebate_amount), platform_rate=Decimal("1.00"),
        ),
        AS_OF,
    )


def test_the_worked_example_is_22_67_points():
    result = _flight()

    assert result.margin == Decimal("823.26")
    assert result.margin_pct == Decimal("22.67")
    assert str(result.margin_pct) == "22.67"


def test_a_negative_margin_has_a_negative_percentage():
    assert margin_percentage(Decimal("-50.00"), Decimal("1000.00")) == Decimal("-5.00")


def test_a_half_rounds_up_in_magnitude():
    assert margin_percentage(Decimal("24.69"), Decimal("200.00")) == Decimal("12.35")  # exactly 12.345
    assert margin_percentage(Decimal("-24.69"), Decimal("200.00")) == Decimal("-12.35")


def test_a_percentage_always_has_two_decimals():
    assert str(margin_percentage(Decimal("0.00"), Decimal("10.00"))) == "0.00"
    assert str(margin_percentage(Decimal("10.00"), Decimal("10.00"))) == "100.00"
    assert str(margin_percentage(Decimal("1.00"), Decimal("3.00"))) == "33.33"


@pytest.mark.parametrize("revenue", [Decimal("0"), Decimal("0.00")])
def test_without_revenue_there_is_no_percentage_and_no_division(revenue: Decimal):
    assert margin_percentage(Decimal("-520.00"), revenue) is None


def test_a_free_flight_has_no_percentage_whatever_its_cost():
    free = _flight(sale_cpm="0.00", rebate_amount="0")

    assert free.revenue == Decimal("0.00") and free.margin < 0
    assert free.margin_pct is None


def test_a_flight_that_has_not_started_has_no_percentage():
    assert _flight(start=date(2026, 10, 1), end=date(2026, 10, 31)).margin_pct is None


def test_a_running_flight_has_the_percentage_of_its_pro_rated_figures():
    running = calculate_flight_margin(
        FlightEconomics(
            flight_start=date(2026, 9, 1), flight_end=date(2026, 9, 30), contracted_impressions=300_000,
            sale_cpm=Decimal("5.00"), delivered_impressions=90_000, media_cost=Decimal("150.00"),
            rebate_amount=Decimal("300.00"), platform_rate=Decimal("1.00"),
        ),
        date(2026, 9, 10),
    )

    assert running.margin == Decimal("160.00") and running.revenue == Decimal("500.00")
    assert running.margin_pct == Decimal("32.00")


def test_a_line_a_campaign_and_the_totals_divide_their_own_sums_not_the_flights_percentages():
    big = _flight()  # revenue 3,631.01, margin 823.26
    small = _flight(contracted_impressions=1000, sale_cpm="10.00", media_cost="1.00", rebate_amount="0", delivered=0)  # 10.00 / 9.00

    line = total_flights([big, small])
    campaign = total_lines([line])

    expected = margin_percentage(big.margin + small.margin, big.revenue + small.revenue)
    assert line.margin_pct == campaign.margin_pct == expected
    assert expected != Decimal("22.67")
    assert expected != (big.margin_pct + small.margin_pct) / 2


def test_a_line_of_free_flights_alone_has_no_percentage_but_mixed_with_priced_ones_it_has():
    free = _flight(sale_cpm="0.00", rebate_amount="0")

    assert total_flights([free]).margin_pct is None
    assert total_flights([free, _flight()]).margin_pct is not None
    assert total_flights([]).margin_pct is None


def test_an_empty_campaign_has_no_percentage():
    assert total_lines([]).margin_pct is None
