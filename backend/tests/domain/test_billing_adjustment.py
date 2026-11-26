"""The rules of a manual billing adjustment (finance/billing-adjustment), without a database."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.domain.exceptions import BillingAdjustmentError, TargetLineNotAdjustableError
from app.domain.services.billing_adjustment import validate_adjustment
from app.domain.value_objects.billing import BillingAdjustment, BillingBasis

AUGUST_END = date(2026, 8, 31)
D_MINUS_1 = date(2026, 8, 31)


def _validate(**overrides: Any) -> BillingAdjustment:
    values: dict[str, Any] = {
        "basis": BillingBasis.CONTRACTED, "amount": None, "reason": "Acuerdo", "is_target_line": False,
        "flight_end": AUGUST_END, "frozen": False, "as_of": D_MINUS_1,
    }
    values.update(overrides)
    return validate_adjustment(**values)


def _code(**overrides: Any) -> str:
    with pytest.raises(BillingAdjustmentError) as raised:
        _validate(**overrides)
    return raised.value.code


@pytest.mark.parametrize("basis", [BillingBasis.MINIMUM, BillingBasis.DELIVERED, BillingBasis.CONTRACTED])
def test_the_recomputed_bases_are_accepted_without_an_amount(basis: BillingBasis) -> None:
    assert _validate(basis=basis) == BillingAdjustment(basis, None)


def test_a_custom_amount_is_accepted_zero_included() -> None:
    assert _validate(basis=BillingBasis.CUSTOM, amount=Decimal("4200.00")).amount == Decimal("4200.00")
    assert _validate(basis=BillingBasis.CUSTOM, amount=Decimal("0.00")).amount == Decimal("0.00")


@pytest.mark.parametrize(
    "overrides",
    [
        {"basis": BillingBasis.CUSTOM},
        {"basis": BillingBasis.CONTRACTED, "amount": Decimal("1.00")},
        {"basis": BillingBasis.CUSTOM, "amount": Decimal("-0.01")},
        {"basis": BillingBasis.CUSTOM, "amount": Decimal("1.005")},
        {"basis": BillingBasis.REPORTED},
        {"reason": ""},
        {"reason": "  \n"},
    ],
    ids=["custom-no-amount", "amount-with-contracted", "negative", "three-decimals", "reported", "no-reason", "blank-reason"],
)
def test_an_adjustment_that_is_not_well_formed_is_refused(overrides: dict[str, Any]) -> None:
    assert _code(**overrides) == "invalid_adjustment"


def test_a_target_line_is_not_adjusted() -> None:
    with pytest.raises(TargetLineNotAdjustableError):
        _validate(is_target_line=True)


def test_a_flight_that_has_not_ended_is_not_adjusted() -> None:
    assert _code(flight_end=date(2026, 8, 31), as_of=date(2026, 8, 30)) == "flight_not_ended"


def test_a_flight_ending_on_the_day_counted_has_ended() -> None:
    _validate(flight_end=D_MINUS_1, as_of=D_MINUS_1)


def test_a_frozen_flight_is_not_adjusted() -> None:
    assert _code(frozen=True) == "flight_closed"


def test_the_rules_run_in_the_order_of_the_specification() -> None:
    assert _code(reason="", is_target_line=True, frozen=True, as_of=date(2026, 8, 1)) == "invalid_adjustment"
    with pytest.raises(TargetLineNotAdjustableError):
        _validate(is_target_line=True, frozen=True, as_of=date(2026, 8, 1))
    assert _code(frozen=True, as_of=date(2026, 8, 1)) == "flight_not_ended"
