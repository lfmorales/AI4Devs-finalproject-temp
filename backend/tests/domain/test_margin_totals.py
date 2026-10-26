"""A line total is the exact sum of its flights' rounded amounts; a campaign total, of its lines'."""

from datetime import date
from decimal import Decimal

from app.domain.services.flight_margin import calculate_flight_margin
from app.domain.services.margin_totals import total_flights, total_lines
from app.domain.value_objects.margin import FlightEconomics, FlightMargin

AS_OF = date(2026, 9, 10)


def _flight(
    flight_start: date,
    flight_end: date,
    contracted_impressions: int = 1000,
    sale_cpm: str = "10.00",
    delivered_impressions: int = 0,
    media_cost: str = "0.00",
    rebate_amount: str = "0",
) -> FlightMargin:
    return calculate_flight_margin(
        FlightEconomics(
            flight_start=flight_start,
            flight_end=flight_end,
            contracted_impressions=contracted_impressions,
            sale_cpm=Decimal(sale_cpm),
            delivered_impressions=delivered_impressions,
            media_cost=Decimal(media_cost),
            rebate_amount=Decimal(rebate_amount),
            platform_rate=Decimal("1.00"),
        ),
        as_of=AS_OF,
    )


def _closed(**values: object) -> FlightMargin:
    return _flight(date(2026, 8, 1), date(2026, 8, 31), **values)  # type: ignore[arg-type]


def test_a_line_total_is_the_sum_of_the_rounded_amounts_not_the_rounded_sum():
    # Each flight is 10.004 € exactly: it rounds to 10.00 €. Three of them add to 30.00 €; rounding the
    # unrounded sum (30.012 €) would give 30.01 €.
    flights = [_closed(sale_cpm="10.004") for _ in range(3)]

    total = total_flights(flights)

    assert [flight.revenue for flight in flights] == [Decimal("10.00")] * 3
    assert total.revenue == Decimal("30.00")
    assert total.margin == Decimal("30.00")


def test_the_total_has_every_term_and_the_margin_is_their_difference():
    flights = [
        _closed(contracted_impressions=726_202, sale_cpm="5.00", delivered_impressions=700_000,
                media_cost="1200.00", rebate_amount="907.7525"),
        _closed(contracted_impressions=1000, sale_cpm="10.00", delivered_impressions=1000, media_cost="2.50"),
    ]

    total = total_flights(flights)

    assert total.revenue == Decimal("3641.01")
    assert total.media_cost == Decimal("1202.50")
    assert total.rebate == Decimal("907.75")
    assert total.platform_cost == Decimal("701.00")
    assert total.margin == Decimal("829.76")
    assert total.margin == total.revenue - total.media_cost - total.rebate - total.platform_cost


def test_every_total_is_a_decimal_with_two_places():
    total = total_flights([_closed()])

    for amount in (total.revenue, total.media_cost, total.rebate, total.platform_cost, total.margin):
        assert isinstance(amount, Decimal)
        assert amount.as_tuple().exponent == -2


def test_a_line_without_flights_totals_zero():
    total = total_flights([])

    assert total.revenue == Decimal("0.00")
    assert total.margin == Decimal("0.00")
    assert total.provisional is False
    assert total.flights_counted == 0


def test_a_line_with_a_closed_flight_a_running_one_and_one_not_started():
    closed = _closed()  # August, closed: revenue 10.00
    running = _flight(date(2026, 9, 1), date(2026, 9, 30), contracted_impressions=3000)  # 30 EUR x 10/30 = 10.00
    not_started = _flight(date(2026, 10, 1), date(2026, 10, 31), contracted_impressions=5000)

    total = total_flights([closed, running, not_started])

    assert total.revenue == Decimal("20.00")
    assert total.flights_counted == 2
    assert total.not_started_count == 1
    assert total.provisional is True


def test_a_line_of_closed_flights_only_is_not_provisional():
    total = total_flights([_closed(), _closed()])

    assert total.provisional is False


def test_a_not_started_flight_alone_does_not_make_a_line_provisional():
    total = total_flights([_closed(), _flight(date(2026, 10, 1), date(2026, 10, 31))])

    assert total.provisional is False
    assert total.not_started_count == 1


def test_a_below_cost_flight_is_counted_and_still_in_the_total():
    healthy = _closed()  # margin 10.00
    loss = _closed(media_cost="25.00")  # revenue 10.00, media cost 25.00: margin -15.00

    total = total_flights([healthy, loss])

    assert loss.below_cost is True
    assert total.below_cost_count == 1
    assert total.margin == Decimal("-5.00")
    assert total.media_cost == Decimal("25.00")


def test_a_campaign_total_is_the_sum_of_its_lines():
    first_line = total_flights([_closed(), _closed(media_cost="25.00")])
    second_line = total_flights([_flight(date(2026, 9, 1), date(2026, 9, 30), contracted_impressions=3000)])

    campaign = total_lines([first_line, second_line])

    assert campaign.revenue == first_line.revenue + second_line.revenue
    assert campaign.margin == first_line.margin + second_line.margin
    assert campaign.flights_counted == 3
    assert campaign.below_cost_count == 1
    assert campaign.provisional is True


def test_a_campaign_of_closed_lines_is_not_provisional():
    campaign = total_lines([total_flights([_closed()]), total_flights([_closed()])])

    assert campaign.provisional is False


def test_a_campaign_total_equals_the_sum_of_all_its_flights():
    flights_by_line = [[_closed(sale_cpm="10.004")] * 2, [_closed(sale_cpm="10.004")]]

    campaign = total_lines([total_flights(flights) for flights in flights_by_line])

    assert campaign.revenue == Decimal("30.00")
