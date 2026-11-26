"""The billing of a committed flight (finance/margin-calculation, «The revenue of a committed flight is its billing»,
and finance/billing-adjustment): the lesser of the delivered volume and the cap, or the adjustment in force."""

from decimal import Decimal

import pytest

from app.domain.services.flight_margin import committed_billing
from app.domain.value_objects.billing import Billing, BillingAdjustment, BillingBasis


def _bill(
    contracted: int,
    delivered: str,
    cpm: str = "5.00",
    carryover: int = 0,
    carryover_billable: bool = False,
    adjustment: BillingAdjustment | None = None,
) -> Billing:
    return committed_billing(
        contracted=contracted, carryover=carryover, carryover_billable=carryover_billable,
        delivered=Decimal(delivered), sale_cpm=Decimal(cpm), adjustment=adjustment,
    )


# ---------------------------------------------------------------- the rule of the lesser


def test_a_flight_that_delivered_its_volume_bills_its_contracted_volume() -> None:
    assert _bill(726_202, "726202") == Billing(Decimal("726202"), Decimal("3631.01"), BillingBasis.MINIMUM)


def test_under_delivery_reduces_the_billing() -> None:
    assert _bill(1_000_000, "700000") == Billing(Decimal("700000"), Decimal("3500.00"), BillingBasis.MINIMUM)


def test_over_delivery_does_not_raise_the_billing() -> None:
    assert _bill(291_610, "296052", cpm="6.00") == Billing(Decimal("291610"), Decimal("1749.66"), BillingBasis.MINIMUM)


def test_a_dooh_flight_bills_its_delivered_ots_rounded_once() -> None:
    billing = _bill(300_000, "280000.5000")

    assert billing.billable == Decimal("280000.5000")
    assert billing.amount == Decimal("1400.00")  # 1,400.0025 rounded once


def test_a_half_cent_rounds_up() -> None:
    assert _bill(1_000, "505").amount == Decimal("2.53")  # 2.525


def test_the_amount_is_a_decimal_of_two_places() -> None:
    amount = _bill(1_000_000, "700000").amount

    assert isinstance(amount, Decimal) and amount.as_tuple().exponent == -2


def test_no_delivery_bills_nothing() -> None:
    assert _bill(1_000_000, "0") == Billing(Decimal("0"), Decimal("0.00"), BillingBasis.MINIMUM)


def test_a_carry_over_that_is_not_billable_keeps_the_cap_at_the_contracted_volume() -> None:
    assert _bill(500_000, "580000", carryover=100_000) == Billing(
        Decimal("500000"), Decimal("2500.00"), BillingBasis.MINIMUM
    )


def test_a_billable_carry_over_raises_the_cap() -> None:
    assert _bill(500_000, "580000", carryover=100_000, carryover_billable=True) == Billing(
        Decimal("580000"), Decimal("2900.00"), BillingBasis.MINIMUM
    )


def test_a_billable_carry_over_still_caps_the_billing() -> None:
    assert _bill(500_000, "650000", carryover=100_000, carryover_billable=True).amount == Decimal("3000.00")


# ---------------------------------------------------------------- adjustments


def _adjusted(basis: BillingBasis, amount: str | None = None) -> BillingAdjustment:
    return BillingAdjustment(basis, None if amount is None else Decimal(amount))


def test_the_contracted_basis_bills_the_contracted_volume() -> None:
    assert _bill(1_000_000, "700000", adjustment=_adjusted(BillingBasis.CONTRACTED)) == Billing(
        Decimal("1000000"), Decimal("5000.00"), BillingBasis.CONTRACTED
    )


def test_the_contracted_basis_bills_the_cap_with_or_without_a_billable_carry_over() -> None:
    contracted = _adjusted(BillingBasis.CONTRACTED)

    assert _bill(500_000, "450000", carryover=100_000, adjustment=contracted).amount == Decimal("2500.00")
    assert _bill(500_000, "450000", carryover=100_000, carryover_billable=True, adjustment=contracted) == Billing(
        Decimal("600000"), Decimal("3000.00"), BillingBasis.CONTRACTED
    )


def test_the_delivered_basis_bills_an_over_delivery() -> None:
    assert _bill(1_000_000, "1100000", adjustment=_adjusted(BillingBasis.DELIVERED)) == Billing(
        Decimal("1100000"), Decimal("5500.00"), BillingBasis.DELIVERED
    )


def test_the_delivered_basis_follows_the_delivery() -> None:
    delivered = _adjusted(BillingBasis.DELIVERED)

    assert _bill(1_000_000, "700000", adjustment=delivered).amount == Decimal("3500.00")
    assert _bill(1_000_000, "720000", adjustment=delivered).amount == Decimal("3600.00")


def test_a_custom_amount_is_fixed_and_has_no_volume() -> None:
    custom = _adjusted(BillingBasis.CUSTOM, "4200.00")

    assert _bill(1_000_000, "700000", adjustment=custom) == Billing(None, Decimal("4200.00"), BillingBasis.CUSTOM)
    assert _bill(1_000_000, "900000", adjustment=custom).amount == Decimal("4200.00")


def test_a_custom_amount_of_zero_bills_nothing() -> None:
    assert _bill(1_000_000, "700000", adjustment=_adjusted(BillingBasis.CUSTOM, "0.00")).amount == Decimal("0.00")


def test_the_minimum_basis_returns_to_the_rule() -> None:
    assert _bill(1_000_000, "700000", adjustment=_adjusted(BillingBasis.MINIMUM)) == Billing(
        Decimal("700000"), Decimal("3500.00"), BillingBasis.MINIMUM
    )


@pytest.mark.parametrize(
    ("basis", "amount"),
    [
        (BillingBasis.CUSTOM, None),
        (BillingBasis.CONTRACTED, "100.00"),
        (BillingBasis.DELIVERED, "100.00"),
        (BillingBasis.MINIMUM, "100.00"),
        (BillingBasis.CUSTOM, "-1.00"),
        (BillingBasis.CUSTOM, "1.005"),
        (BillingBasis.REPORTED, None),
    ],
    ids=["custom-without-amount", "contracted-with-amount", "delivered-with-amount", "minimum-with-amount",
         "negative", "three-decimals", "reported-is-not-an-adjustment"],
)
def test_an_invalid_adjustment_is_refused(basis: BillingBasis, amount: str | None) -> None:
    with pytest.raises(ValueError):
        BillingAdjustment(basis, None if amount is None else Decimal(amount))


def test_an_adjustment_amount_must_be_a_decimal() -> None:
    with pytest.raises(TypeError):
        BillingAdjustment(BillingBasis.CUSTOM, 4200.0)  # type: ignore[arg-type]
