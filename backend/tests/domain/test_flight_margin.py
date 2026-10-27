"""The margin of one flight: revenue, media cost, rebate and platform cost, each rounded once, half up.

Worked example (docs/product-description.md §5.8, flight model): 726,202 contracted impressions at a
sale CPM of 5.00 € give revenue 3,631.01 €; the rebate is 25 % of it, 907.7525 € exact, 907.75 € rounded;
700,000 delivered impressions at 1.00 € per thousand give a platform cost of 700.00 €. The media cost of
1,200.00 € is a placeholder, since real cost only exists in Adform.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.services import flight_margin
from app.domain.services.flight_margin import calculate_flight_margin, round_amount
from app.domain.value_objects.margin import FlightEconomics, FlightStatus

AUGUST_START = date(2026, 8, 1)
AUGUST_END = date(2026, 8, 31)
AFTER_AUGUST = date(2026, 9, 1)


def _flight(
    contracted_impressions: int = 726_202,
    sale_cpm: str = "5.00",
    delivered_impressions: int = 700_000,
    media_cost: str = "1200.00",
    rebate_amount: str = "907.7525",
    platform_rate: str = "1.00",
    flight_start: date = AUGUST_START,
    flight_end: date = AUGUST_END,
) -> FlightEconomics:
    return FlightEconomics(
        flight_start=flight_start,
        flight_end=flight_end,
        contracted_impressions=contracted_impressions,
        sale_cpm=Decimal(sale_cpm),
        delivered_impressions=delivered_impressions,
        media_cost=Decimal(media_cost),
        rebate_amount=Decimal(rebate_amount),
        platform_rate=Decimal(platform_rate),
    )


def test_a_closed_flight_applies_the_four_terms():
    result = calculate_flight_margin(_flight(), as_of=AFTER_AUGUST)

    assert result.status is FlightStatus.CLOSED
    assert result.revenue == Decimal("3631.01")
    assert result.media_cost == Decimal("1200.00")
    assert result.rebate == Decimal("907.75")
    assert result.platform_cost == Decimal("700.00")
    assert result.margin == Decimal("823.26")
    assert result.provisional is False
    assert result.below_cost is False


def test_every_output_amount_is_a_decimal_with_two_places():
    result = calculate_flight_margin(_flight(), as_of=AFTER_AUGUST)

    for amount in (result.revenue, result.media_cost, result.rebate, result.platform_cost, result.margin):
        assert isinstance(amount, Decimal)
        assert amount.as_tuple().exponent == -2


def test_rounding_is_half_up_not_half_even():
    assert round_amount(Decimal("0.125")) == Decimal("0.13")
    assert round_amount(Decimal("2.525")) == Decimal("2.53")
    assert round_amount(Decimal("0.124999")) == Decimal("0.12")


def test_the_rebate_is_rounded_before_the_margin_is_subtracted():
    # The margin subtracts the rounded 0.13, not the exact 0.125.
    result = calculate_flight_margin(_flight(rebate_amount="0.125"), as_of=AFTER_AUGUST)

    assert result.rebate == Decimal("0.13")
    assert result.margin == Decimal("3631.01") - Decimal("1200.00") - Decimal("0.13") - Decimal("700.00")


def test_each_amount_is_rounded_exactly_once(monkeypatch: pytest.MonkeyPatch):
    calls: list[Decimal] = []
    original = flight_margin.round_amount

    def spy(amount: Decimal) -> Decimal:
        calls.append(amount)
        return original(amount)

    monkeypatch.setattr(flight_margin, "round_amount", spy)

    calculate_flight_margin(_flight(), as_of=AFTER_AUGUST)

    assert len(calls) == 4


def test_a_float_input_is_refused():
    with pytest.raises(TypeError):
        FlightEconomics(
            flight_start=AUGUST_START,
            flight_end=AUGUST_END,
            contracted_impressions=1000,
            sale_cpm=5.0,  # type: ignore[arg-type]
            delivered_impressions=0,
            media_cost=Decimal("0"),
            rebate_amount=Decimal("0"),
            platform_rate=Decimal("1.00"),
        )


def test_under_delivery_does_not_reduce_revenue():
    result = calculate_flight_margin(_flight(delivered_impressions=700_000), as_of=AFTER_AUGUST)

    assert result.revenue == Decimal("3631.01")
    assert result.platform_cost == Decimal("700.00")


@pytest.mark.parametrize("delivered", [0, 700_000, 726_202, 900_000])
def test_revenue_is_the_same_whatever_was_delivered(delivered: int):
    result = calculate_flight_margin(_flight(delivered_impressions=delivered), as_of=AFTER_AUGUST)

    assert result.revenue == Decimal("3631.01")


SEPTEMBER_START = date(2026, 9, 1)
SEPTEMBER_END = date(2026, 9, 30)


def _september_flight(**overrides: object) -> FlightEconomics:
    """A 30-day flight: 300,000 contracted at 5.00 € is 1,500.00 € in full, with a flat 20 % rebate of 300.00 €."""
    values: dict[str, object] = {
        "contracted_impressions": 300_000,
        "sale_cpm": "5.00",
        "delivered_impressions": 90_000,
        "media_cost": "150.00",
        "rebate_amount": "300.00",
        "platform_rate": "1.00",
        "flight_start": SEPTEMBER_START,
        "flight_end": SEPTEMBER_END,
    }
    values.update(overrides)
    return _flight(**values)  # type: ignore[arg-type]


def test_a_running_flight_is_pro_rated_by_elapsed_days_of_its_window():
    # Ten of thirty days have elapsed on September 10th:
    #   revenue  1,500.00 x 10 / 30 = 500.00
    #   rebate     300.00 x 10 / 30 = 100.00
    #   media cost and platform cost come from what was delivered, so they are not pro-rated:
    #   media cost 150.00; platform cost 90,000 / 1000 x 1.00 = 90.00
    #   margin 500.00 - 150.00 - 100.00 - 90.00 = 160.00
    result = calculate_flight_margin(_september_flight(), as_of=date(2026, 9, 10))

    assert result.status is FlightStatus.RUNNING
    assert result.revenue == Decimal("500.00")
    assert result.rebate == Decimal("100.00")
    assert result.media_cost == Decimal("150.00")
    assert result.platform_cost == Decimal("90.00")
    assert result.margin == Decimal("160.00")
    assert result.provisional is True


def test_a_running_flight_with_no_delivery_still_accrues_revenue():
    result = calculate_flight_margin(
        _september_flight(delivered_impressions=0, media_cost="0.00"), as_of=date(2026, 9, 10)
    )

    assert result.status is FlightStatus.RUNNING
    assert result.revenue == Decimal("500.00")
    assert result.platform_cost == Decimal("0.00")
    assert result.margin == Decimal("400.00")
    assert result.provisional is True


@pytest.mark.parametrize("delivered", [0, 90_000, 400_000])
def test_pro_rating_does_not_depend_on_what_was_delivered(delivered: int):
    result = calculate_flight_margin(_september_flight(delivered_impressions=delivered), as_of=date(2026, 9, 10))

    assert result.revenue == Decimal("500.00")
    assert result.rebate == Decimal("100.00")


def test_the_flight_is_closed_on_the_day_its_last_day_is_counted():
    result = calculate_flight_margin(_september_flight(), as_of=SEPTEMBER_END)

    assert result.status is FlightStatus.CLOSED
    assert result.revenue == Decimal("1500.00")
    assert result.provisional is False


def test_the_day_before_the_end_is_still_running():
    result = calculate_flight_margin(_september_flight(), as_of=date(2026, 9, 29))

    assert result.status is FlightStatus.RUNNING
    assert result.revenue == Decimal("1450.00")  # 1,500.00 x 29 / 30
    assert result.provisional is True


def test_the_first_day_of_a_flight_is_one_elapsed_day():
    result = calculate_flight_margin(_september_flight(), as_of=SEPTEMBER_START)

    assert result.status is FlightStatus.RUNNING
    assert result.revenue == Decimal("50.00")  # 1,500.00 x 1 / 30


def test_a_flight_that_has_not_started_has_no_margin():
    result = calculate_flight_margin(
        _september_flight(flight_start=date(2026, 10, 1), flight_end=date(2026, 10, 31)), as_of=SEPTEMBER_END
    )

    assert result.status is FlightStatus.NOT_STARTED
    assert result.revenue is None
    assert result.media_cost is None
    assert result.rebate is None
    assert result.platform_cost is None
    assert result.margin is None
    assert result.provisional is False
    assert result.below_cost is False


def test_a_pro_rated_amount_is_rounded_once_after_pro_rating():
    # 1,001 impressions at 5.00 € is exactly 5.005 €. Over two days, one elapsed, the exact figure is 2.5025,
    # which rounds to 2.50; rounding the full amount first (5.01) and halving it would give 2.51.
    flight = _flight(
        contracted_impressions=1001,
        rebate_amount="5.005",
        flight_start=date(2026, 9, 1),
        flight_end=date(2026, 9, 2),
        delivered_impressions=0,
        media_cost="0.00",
    )

    result = calculate_flight_margin(flight, as_of=date(2026, 9, 1))

    assert result.revenue == Decimal("2.50")
    assert result.rebate == Decimal("2.50")


def test_a_running_flight_also_rounds_each_amount_exactly_once(monkeypatch: pytest.MonkeyPatch):
    calls: list[Decimal] = []
    original = flight_margin.round_amount
    monkeypatch.setattr(flight_margin, "round_amount", lambda amount: calls.append(amount) or original(amount))

    calculate_flight_margin(_september_flight(), as_of=date(2026, 9, 10))

    assert len(calls) == 4


def test_a_flight_whose_media_cost_exceeds_its_revenue_is_below_cost():
    result = calculate_flight_margin(_flight(media_cost="4000.00", rebate_amount="0"), as_of=AFTER_AUGUST)

    assert result.below_cost is True
    assert result.margin == Decimal("3631.01") - Decimal("4000.00") - Decimal("700.00")


def test_a_margin_of_exactly_zero_is_not_below_cost():
    # Revenue 3,631.01 = media cost, no rebate, no platform cost: the final margin is 0.00.
    result = calculate_flight_margin(
        _flight(media_cost="3631.01", rebate_amount="0", platform_rate="0"), as_of=AFTER_AUGUST
    )

    assert result.margin == Decimal("0.00")
    assert result.below_cost is False


def test_below_cost_judges_the_margin_made_of_rounded_amounts():
    # A media cost of 100.004 rounds to 100.00 against a revenue of 100.00: the margin is 0.00, not -0.004.
    result = calculate_flight_margin(
        _flight(contracted_impressions=10_000, sale_cpm="10.00", media_cost="100.004", rebate_amount="0", platform_rate="0"),
        as_of=AFTER_AUGUST,
    )

    assert result.revenue == Decimal("100.00") and result.media_cost == Decimal("100.00")
    assert result.margin == Decimal("0.00")
    assert result.below_cost is False


def test_a_cent_under_zero_is_below_cost():
    result = calculate_flight_margin(
        _flight(contracted_impressions=10_000, sale_cpm="10.00", media_cost="100.01", rebate_amount="0", platform_rate="0"),
        as_of=AFTER_AUGUST,
    )

    assert result.margin == Decimal("-0.01")
    assert result.below_cost is True


def test_a_flight_with_media_cost_under_revenue_is_below_cost_when_the_rebate_and_platform_take_it_under_zero():
    # Media cost 2,100.00 against revenue 3,631.01, but the rebate (907.75) and the platform cost (700.00) follow.
    result = calculate_flight_margin(_flight(media_cost="2100.00"), as_of=AFTER_AUGUST)

    assert result.media_cost < result.revenue
    assert result.margin == Decimal("-76.74")
    assert result.below_cost is True


def test_a_flight_whose_media_cost_equals_its_revenue_is_below_cost_once_the_other_costs_are_counted():
    result = calculate_flight_margin(_flight(media_cost="3631.01"), as_of=AFTER_AUGUST)

    assert result.below_cost is True


def test_a_positive_margin_is_not_below_cost_even_with_a_high_media_cost():
    result = calculate_flight_margin(
        _flight(media_cost="3000.00", rebate_amount="0", platform_rate="0.10"), as_of=AFTER_AUGUST
    )

    assert result.margin == Decimal("3631.01") - Decimal("3000.00") - Decimal("70.00")
    assert result.below_cost is False


def test_a_running_flight_can_be_below_cost():
    result = calculate_flight_margin(_september_flight(media_cost="900.00"), as_of=date(2026, 9, 10))

    assert result.below_cost is True
