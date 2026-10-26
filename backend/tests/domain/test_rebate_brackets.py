"""Marginal brackets: each euro of a flight's revenue accrues at the bracket its position in the counter falls in.

Worked examples (docs/product-description.md §5.4): a counter at 90,000 € receiving 30,000 € with brackets of
15 % up to 100,000 € and 20 % above gives 1,500 + 4,000 = 5,500 €, a blended 18.33 %; 600,000 € over 15/20/25 %
brackets cut at 100,000 and 500,000 € gives 120,000 €, 20.0 %, not 25 % of the lot.
"""

from decimal import Decimal

import pytest

from app.domain.exceptions import RebateRuleError
from app.domain.services.rebate_brackets import apply_brackets
from app.domain.value_objects.rebate import Bracket

TWO_BRACKETS = (
    Bracket(Decimal(0), Decimal(100_000), Decimal("0.15")),
    Bracket(Decimal(100_000), None, Decimal("0.20")),
)
THREE_BRACKETS = (
    Bracket(Decimal(0), Decimal(100_000), Decimal("0.15")),
    Bracket(Decimal(100_000), Decimal(500_000), Decimal("0.20")),
    Bracket(Decimal(500_000), None, Decimal("0.25")),
)


def test_a_flight_across_a_cut_is_split_between_the_two_brackets():
    result = apply_brackets(TWO_BRACKETS, Decimal(90_000), Decimal(30_000))

    assert [(charge.amount, charge.rate, charge.rebate) for charge in result.charges] == [
        (Decimal(10_000), Decimal("0.15"), Decimal(1_500)),
        (Decimal(20_000), Decimal("0.20"), Decimal(4_000)),
    ]
    assert result.rebate == Decimal(5_500)
    assert result.effective_rate.quantize(Decimal("0.0001")) == Decimal("0.1833")


def test_six_hundred_thousand_over_three_brackets_is_twenty_percent():
    result = apply_brackets(THREE_BRACKETS, Decimal(0), Decimal(600_000))

    assert [charge.rebate for charge in result.charges] == [Decimal(15_000), Decimal(80_000), Decimal(25_000)]
    assert result.rebate == Decimal(120_000)
    assert result.effective_rate == Decimal("0.2")


def test_a_flat_rate_on_a_real_revenue_is_exact_and_unrounded():
    flat = (Bracket(Decimal(0), None, Decimal("0.25")),)

    result = apply_brackets(flat, Decimal(0), Decimal("3631.01"))

    assert result.rebate == Decimal("907.7525")


def test_a_flight_of_ten_euros_crossing_a_cut_by_fifty_cents():
    result = apply_brackets(TWO_BRACKETS, Decimal("99999.50"), Decimal("10.00"))

    assert [(charge.amount, charge.rebate) for charge in result.charges] == [
        (Decimal("0.50"), Decimal("0.0750")),
        (Decimal("9.50"), Decimal("1.9000")),
    ]
    assert result.rebate == Decimal("1.975")


def test_a_counter_exactly_on_a_cut_starts_the_next_bracket():
    result = apply_brackets(TWO_BRACKETS, Decimal(100_000), Decimal(1_000))

    assert len(result.charges) == 1
    assert result.charges[0].rate == Decimal("0.20")
    assert result.rebate == Decimal(200)


def test_a_flight_ending_exactly_on_a_cut_stays_in_the_lower_bracket():
    result = apply_brackets(TWO_BRACKETS, Decimal(99_000), Decimal(1_000))

    assert len(result.charges) == 1
    assert result.charges[0].rate == Decimal("0.15")
    assert result.rebate == Decimal(150)


def test_a_flight_spanning_three_brackets_charges_all_three():
    result = apply_brackets(THREE_BRACKETS, Decimal(90_000), Decimal(500_000))

    assert [charge.amount for charge in result.charges] == [Decimal(10_000), Decimal(400_000), Decimal(90_000)]
    assert result.rebate == Decimal(1_500 + 80_000 + 22_500)


def test_the_rebate_is_reproducible_from_the_breakdown():
    result = apply_brackets(THREE_BRACKETS, Decimal("91234.56"), Decimal("456789.01"))

    assert sum((charge.amount * charge.rate for charge in result.charges), Decimal(0)) == result.rebate
    assert sum((charge.amount for charge in result.charges), Decimal(0)) == Decimal("456789.01")


def test_a_flight_without_revenue_accrues_nothing():
    result = apply_brackets(TWO_BRACKETS, Decimal(50_000), Decimal(0))

    assert result.charges == ()
    assert result.rebate == Decimal(0)
    assert result.effective_rate == Decimal(0)


def test_negative_revenue_is_a_domain_error():
    with pytest.raises(RebateRuleError) as raised:
        apply_brackets(TWO_BRACKETS, Decimal(0), Decimal("-1"))

    assert raised.value.code == "revenue_must_not_be_negative"


def test_a_float_is_refused():
    with pytest.raises(TypeError):
        apply_brackets(TWO_BRACKETS, 0.0, Decimal(1))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Bracket(Decimal(0), None, 0.15)  # type: ignore[arg-type]
