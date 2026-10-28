"""A line without a price: a sale CPM of 0.00 with positive volume. No revenue, no rebate, the cost remains."""

from datetime import date
from decimal import Decimal

from app.domain.services.flight_margin import calculate_flight_margin
from app.domain.services.margin_totals import total_flights, total_lines
from app.domain.services.priced_flights import price_flights
from app.domain.value_objects.margin import FlightEconomics, FlightStatus
from app.domain.value_objects.priced_flight import PlatformRates
from tests.domain.test_priced_flights import AGENCY, GROUP, facts, schedule

AS_OF = date(2026, 9, 5)
AUGUST = (date(2026, 8, 1), date(2026, 8, 31))


def _economics(sale_cpm: str = "0.00", **overrides: object) -> FlightEconomics:
    values: dict[str, object] = {
        "flight_start": AUGUST[0], "flight_end": AUGUST[1], "contracted_impressions": 500_000,
        "sale_cpm": Decimal(sale_cpm), "delivered_impressions": 400_000, "media_cost": Decimal("120.00"),
        "rebate_amount": Decimal("0"), "platform_rate": Decimal("1.00"),
    }
    values.update(overrides)
    return FlightEconomics(**values)  # type: ignore[arg-type]


def test_a_flight_without_a_price_has_no_revenue_and_a_margin_of_minus_its_costs():
    result = calculate_flight_margin(_economics(), AS_OF)

    assert result.revenue == Decimal("0.00")
    assert result.rebate == Decimal("0.00")
    assert result.media_cost == Decimal("120.00")
    assert result.platform_cost == Decimal("400.00")
    assert result.margin == Decimal("-520.00")
    assert result.zero_sale is True
    assert result.below_cost is True


def test_a_flight_with_a_price_is_not_zero_sale():
    assert calculate_flight_margin(_economics(sale_cpm="5.00"), AS_OF).zero_sale is False


def test_a_flight_that_has_not_started_is_not_zero_sale():
    result = calculate_flight_margin(_economics(), date(2026, 7, 31))

    assert result.status is FlightStatus.NOT_STARTED
    assert result.zero_sale is False


def test_a_running_flight_without_a_price_is_zero_sale_and_provisional():
    result = calculate_flight_margin(_economics(), date(2026, 8, 10))

    assert result.status is FlightStatus.RUNNING
    assert (result.zero_sale, result.provisional, result.revenue) == (True, True, Decimal("0.00"))
    assert result.margin == Decimal("-520.00")


def test_a_free_flight_without_cost_has_a_margin_of_zero_and_is_not_below_cost():
    result = calculate_flight_margin(_economics(delivered_impressions=0, media_cost=Decimal("0")), AS_OF)

    assert result.margin == Decimal("0.00")
    assert (result.zero_sale, result.below_cost) == (True, False)


def test_the_rebate_is_zero_even_under_a_flat_schedule_and_the_counter_does_not_move():
    free = facts(flight_id=1, flight_start=date(2026, 7, 1), flight_end=date(2026, 7, 31), contracted_impressions=500_000,
                 sale_cpm="0.00", delivered_impressions=400_000, media_cost="120.00")
    priced = facts(flight_id=2, contracted_impressions=6_000_000, sale_cpm="5.00", delivered_impressions=0, media_cost="0")

    first, second = price_flights([schedule()], PlatformRates(system=Decimal("1.00")), [free, priced], AS_OF)

    assert first.margin.zero_sale is True
    assert first.rebate.rebate == Decimal(0)
    assert first.rebate.position_after == first.rebate.position_before == Decimal(0)
    assert second.rebate.position_before == Decimal(0)
    assert second.margin.zero_sale is False
    assert second.rebate.rebate == Decimal(7_500)  # 25 % of 30,000


def test_the_synthetic_line_through_the_whole_pricing_function():
    free = facts(contracted_impressions=500_000, sale_cpm="0.00", delivered_impressions=400_000, media_cost="120.00")

    (priced,) = price_flights([schedule()], PlatformRates(system=Decimal("1.00")), [free], AS_OF)

    assert (priced.margin.revenue, priced.margin.rebate, priced.margin.margin) == (
        Decimal("0.00"), Decimal("0.00"), Decimal("-520.00"))
    assert priced.margin.zero_sale is True


def test_zero_sale_is_counted_in_the_line_the_campaign_and_the_totals():
    free = calculate_flight_margin(_economics(), AS_OF)
    priced = calculate_flight_margin(_economics(sale_cpm="5.00"), AS_OF)

    free_line = total_flights([free, priced])
    priced_line = total_flights([priced])
    campaign = total_lines([free_line, priced_line])

    assert (free_line.zero_sale_count, priced_line.zero_sale_count, campaign.zero_sale_count) == (1, 0, 1)
    assert (free_line.zero_sale, priced_line.zero_sale, campaign.zero_sale) == (True, False, True)
    assert free_line.revenue == priced.revenue
    assert free_line.margin == free.margin + priced.margin


def test_a_total_of_a_free_line_alone_has_zero_revenue():
    line = total_flights([calculate_flight_margin(_economics(), AS_OF)])

    assert line.revenue == Decimal("0.00")
    assert line.margin == Decimal("-520.00")
    assert line.below_cost_count == 1
