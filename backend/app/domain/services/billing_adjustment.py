"""The rules of a manual billing adjustment (finance/billing-adjustment)."""

from datetime import date
from decimal import Decimal

from app.domain.exceptions import BillingAdjustmentError, TargetLineNotAdjustableError
from app.domain.value_objects.billing import BillingAdjustment, BillingBasis


def validate_adjustment(
    *,
    basis: BillingBasis,
    amount: Decimal | None,
    reason: str,
    is_target_line: bool,
    flight_end: date,
    frozen: bool,
    as_of: date,
) -> BillingAdjustment:
    """The adjustment a request asks for, or the first rule it breaks: its own shape (a reason, an amount only with the
    `custom` basis, zero or above, two decimals at most), then a target line, a flight that has not ended and a frozen
    one. `as_of` is D-1, the last day counted: a flight ending on it has ended."""
    try:
        adjustment = BillingAdjustment(basis, amount)
    except ValueError as error:
        raise BillingAdjustmentError("invalid_adjustment", str(error)) from None
    if not reason or not reason.strip():
        raise BillingAdjustmentError("invalid_adjustment", "an adjustment needs a reason")
    if is_target_line:
        raise TargetLineNotAdjustableError("a target line bills what its DSP reports: it cannot be adjusted")
    if flight_end > as_of:
        raise BillingAdjustmentError("flight_not_ended", "only a flight that has ended can be adjusted")
    if frozen:
        raise BillingAdjustmentError("flight_closed", "a flight frozen by a closing cannot be adjusted")
    return adjustment
