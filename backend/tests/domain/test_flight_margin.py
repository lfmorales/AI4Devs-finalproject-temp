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
