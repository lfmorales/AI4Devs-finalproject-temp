"""The billing of a flight: how much GeoQ invoices for it, on what volume and by which rule."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class BillingBasis(StrEnum):
    """How a flight's billing was reached.

    `minimum` is the rule of the lesser of the delivered volume and the cap; `delivered`, `contracted` and `custom` are
    the bases of a manual adjustment; `reported` is a target flight's, which bills what its DSP reports.
    """

    MINIMUM = "minimum"
    DELIVERED = "delivered"
    CONTRACTED = "contracted"
    CUSTOM = "custom"
    REPORTED = "reported"


ADJUSTMENT_BASES = frozenset({BillingBasis.MINIMUM, BillingBasis.DELIVERED, BillingBasis.CONTRACTED, BillingBasis.CUSTOM})
_CENT_EXPONENT = -2


@dataclass(frozen=True)
class BillingAdjustment:
    """The adjustment in force on a committed flight: its basis and, only for `custom`, its amount, zero or above and
    with at most two decimals. Its reason, author and moment are kept with it but never price anything."""

    basis: BillingBasis
    amount: Decimal | None

    def __post_init__(self) -> None:
        if self.basis not in ADJUSTMENT_BASES:
            raise ValueError(f"{self.basis.value} is not the basis of an adjustment")
        if self.amount is not None and not isinstance(self.amount, Decimal):
            raise TypeError(f"amount must be a Decimal, not {type(self.amount).__name__}")
        if (self.basis is BillingBasis.CUSTOM) != (self.amount is not None):
            raise ValueError("an amount is given with the custom basis, and only with it")
        if self.amount is not None:
            if self.amount < 0:
                raise ValueError("the amount of an adjustment must not be negative")
            exponent = self.amount.as_tuple().exponent
            if not isinstance(exponent, int) or exponent < _CENT_EXPONENT:
                raise ValueError("the amount of an adjustment has at most two decimals")


@dataclass(frozen=True)
class Billing:
    """What a committed flight bills: the billable volume in the unit of its delivery metric (none for a custom amount), the
    amount rounded once to two decimals, and the basis it was reached by."""

    billable: Decimal | None
    amount: Decimal
    basis: BillingBasis


@dataclass(frozen=True)
class AdjustmentEntry:
    """One stored adjustment of a flight, with its reason, its author and its moment. The latest of a flight is in force."""

    entry_id: int
    flight_id: int
    adjustment: BillingAdjustment
    reason: str
    created_by: int
    created_at: datetime
