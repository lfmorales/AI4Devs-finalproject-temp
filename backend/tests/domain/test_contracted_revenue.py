"""contracted_revenue (the sale of the whole flight) and the accrued/window days next to the revenue.

Since committed-billing-and-review a committed flight's revenue is its billing, the lesser of delivered and contracted,
so the contracted sale is an informative figure that the revenue reaches only when the whole volume was delivered.
"""

from datetime import date
from decimal import Decimal

from app.domain.services.flight_margin import calculate_flight_margin
from app.domain.services.margin_totals import total_flights, total_lines
from app.domain.value_objects.margin import FlightStatus
from tests.fixtures.flight_inputs import flight_economics

AS_OF = date(2026, 8, 10)


def _flight(
    start: date = date(2026, 8, 1), end: date = date(2026, 8, 31), contracted: int = 1_000_000, cpm: str = "5.00",
    delivered: int = 0,
):
    return calculate_flight_margin(
        flight_economics(
            flight_start=start, flight_end=end, contracted_impressions=contracted, sale_cpm=Decimal(cpm),
            delivered_impressions=delivered, media_cost=Decimal("0"), rebate_amount=Decimal("0"),
            platform_rate=Decimal("1.00"),
        ),
        AS_OF,
    )


# Changed by committed-billing-and-review: the revenue of a running flight was 5000 x 10 / 31 = 1,612.90; it is now its
# billing to date, 180,000 delivered at 5.00 € = 900.00, and the days drive no amount.
def test_a_running_flight_has_the_whole_sale_and_fewer_accrued_days_than_window_days():
    result = _flight(delivered=180_000)

    assert result.status is FlightStatus.RUNNING
    assert result.contracted_revenue == Decimal("5000.00")
    assert result.revenue == Decimal("900.00")
    assert (result.accrued_days, result.window_days) == (10, 31)
    assert result.accrued_days < result.window_days


# Changed: a closed flight accrued all of its contracted sale whatever it delivered; it now bills it all only when it
# delivered its whole volume, and less when it under-delivered.
def test_a_closed_flight_that_delivered_its_volume_bills_all_of_it():
    result = _flight(end=date(2026, 8, 10), delivered=1_000_000)

    assert result.status is FlightStatus.CLOSED
    assert result.revenue == result.contracted_revenue == Decimal("5000.00")
    assert (result.accrued_days, result.window_days) == (10, 10)


def test_a_closed_flight_that_under_delivered_bills_less_than_its_contracted_sale() -> None:
    result = _flight(end=date(2026, 8, 10), delivered=700_000)

    assert (result.contracted_revenue, result.revenue) == (Decimal("5000.00"), Decimal("3500.00"))


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


# Changed: the running revenue was the pro-rated sale, 1,612.90; it is now the billing to date, nothing when nothing
# was delivered, and still provisional.
def test_a_running_flight_s_revenue_is_its_billing_to_date_and_provisional():
    assert (_flight().revenue, _flight().provisional) == (Decimal("0.00"), True)
    assert _flight(delivered=180_000).revenue == Decimal("900.00")


# ---------------------------------------------------------------- the volumes behind the amounts

def _with_delivery(delivered: int, contracted: int = 1_000_000, start: date = date(2026, 8, 1), end: date = date(2026, 8, 31)):
    return calculate_flight_margin(
        flight_economics(
            flight_start=start, flight_end=end, contracted_impressions=contracted, sale_cpm=Decimal("5.00"),
            delivered_impressions=delivered, media_cost=Decimal("0"), rebate_amount=Decimal("0"), platform_rate=Decimal("1.00"),
        ),
        AS_OF,
    )


def test_a_flight_carries_its_delivered_and_contracted_impressions():
    result = _with_delivery(delivered=300_000)

    assert (result.delivered_impressions, result.contracted_impressions) == (300_000, 1_000_000)


def test_a_flight_that_has_not_started_carries_neither_volume():
    result = _with_delivery(delivered=0, start=date(2026, 8, 11))

    assert (result.delivered_impressions, result.contracted_impressions) == (None, None)


def test_the_volumes_add_exactly_by_line_and_by_campaign_and_skip_the_flights_not_started():
    flights = [_with_delivery(300_000, 1_000_000), _with_delivery(250_001, 400_000), _with_delivery(0, 700_000, start=date(2026, 8, 11))]

    line = total_flights(flights)

    assert (line.delivered_impressions, line.contracted_impressions) == (550_001, 1_400_000)
    campaign = total_lines([line, total_flights([_with_delivery(7, 9)])])
    assert (campaign.delivered_impressions, campaign.contracted_impressions) == (550_008, 1_400_009)
    assert isinstance(campaign.delivered_impressions, int) and isinstance(campaign.contracted_impressions, int)
