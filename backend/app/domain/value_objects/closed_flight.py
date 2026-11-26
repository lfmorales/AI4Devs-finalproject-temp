from dataclasses import dataclass
from decimal import Decimal

from app.domain.value_objects.billing import BillingBasis
from app.domain.value_objects.volume_commitment import VolumeCommitment

_VOLUME_BASES = frozenset({BillingBasis.MINIMUM, BillingBasis.DELIVERED, BillingBasis.CONTRACTED})
_ADJUSTED_BASES = frozenset({BillingBasis.DELIVERED, BillingBasis.CONTRACTED, BillingBasis.CUSTOM})
_DECIMAL_FIELDS = (
    "revenue", "contracted_revenue", "media_cost", "rebate", "platform_cost", "margin", "delivered",
    "window_media_cost", "window_reported_revenue", "window_buyer_spend", "window_data_cost", "sale_cpm",
)


@dataclass(frozen=True)
class ClosedFlightSnapshot:
    """What the closing of a month froze of one flight: a closed flight is read from it and never computed again.

    The amounts are the final ones, rounded once as the closing showed them. `gross_revenue` is a target flight's only:
    a committed flight has none. The delivery they were computed on is kept, unrounded where the window sums are, so that
    the current delivery can be compared with it: `delivered_impressions`, `delivered` in the unit of `delivery_metric`,
    and the window's media cost, reported revenue, buyer's spend and data costs. The line's `sale_cpm`,
    `contracted_impressions` and `volume_commitment` are those of the moment of the closing.

    The billing is frozen with them: `billing_basis`, `billable` (in the unit of `delivery_metric`, none for a custom
    amount or a target flight), the `carryover` and whether it was billable, and the adjustment in force, if any. A
    snapshot written before committed-billing-and-review has none of them, and keeps its revenue as the closing froze it.
    """

    revenue: Decimal
    contracted_revenue: Decimal
    media_cost: Decimal
    rebate: Decimal
    platform_cost: Decimal
    margin: Decimal
    gross_revenue: Decimal | None
    delivered_impressions: int
    delivered: Decimal
    window_media_cost: Decimal
    window_reported_revenue: Decimal
    window_buyer_spend: Decimal
    window_data_cost: Decimal
    gross_differs_from_buyer_spend: bool
    data_cost_reported: bool
    delivery_metric: str
    sale_cpm: Decimal
    contracted_impressions: int
    volume_commitment: VolumeCommitment
    billing_basis: BillingBasis | None = None
    billable: Decimal | None = None
    carryover: int | None = None
    carryover_billable: bool | None = None
    billing_adjustment_id: int | None = None

    def __post_init__(self) -> None:
        for name in _DECIMAL_FIELDS:
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal, not {type(value).__name__}")
        is_target = self.volume_commitment is VolumeCommitment.TARGET
        if is_target and self.gross_revenue is None:
            raise ValueError("a target flight's snapshot needs its gross")
        if not is_target and self.gross_revenue is not None:
            raise ValueError("a committed flight's snapshot has no gross")
        if self.gross_revenue is not None and not isinstance(self.gross_revenue, Decimal):
            raise TypeError(f"gross_revenue must be a Decimal, not {type(self.gross_revenue).__name__}")
        self._check_billing(is_target)

    def _check_billing(self, is_target: bool) -> None:
        """The frozen billing holds together, or is absent altogether, as in a snapshot closed before it existed."""
        if self.billable is not None and not isinstance(self.billable, Decimal):
            raise TypeError(f"billable must be a Decimal, not {type(self.billable).__name__}")
        basis = self.billing_basis
        if basis is None:
            if (self.billable, self.carryover, self.carryover_billable, self.billing_adjustment_id) != (None,) * 4:
                raise ValueError("a snapshot without a billing basis holds no billing")
            return
        if self.carryover is None or self.carryover_billable is None:
            raise ValueError("a snapshot with a billing basis holds its carry-over and whether it was billable")
        if self.carryover < 0:
            raise ValueError("the carry-over of a snapshot must not be negative")
        if is_target != (basis is BillingBasis.REPORTED):
            raise ValueError("a target flight is billed as reported, and only a target flight")
        if (basis in _VOLUME_BASES) != (self.billable is not None):
            raise ValueError(f"the {basis.value} basis {'needs' if basis in _VOLUME_BASES else 'has no'} billable volume")
        if basis in _ADJUSTED_BASES and self.billing_adjustment_id is None:
            raise ValueError(f"the {basis.value} basis is an adjustment's, so the snapshot names it")


@dataclass(frozen=True)
class ClosedDeliveryCheck:
    """A closed flight compared with the delivery stored now in its window: informative, it changes no figure.

    Every difference is the current value less the frozen one. The amounts are rounded to the cent before subtracting
    and `delivered_difference` has four decimals, in the unit of the flight's metric. The reported revenue and the
    buyer's spend are a target flight's only, None for a committed one. The billable volume (four decimals) and the
    billing are a committed flight's closed with its billing frozen, None for a target flight and for a snapshot written
    before it. `current_margin` is the frozen margin's formula with only the delivery changed: the closing's rebate and
    platform rate, and a committed flight's current billing, or its frozen revenue when its snapshot has no billing.
    `changed` is the flag: a margin or a delivered volume that moved beyond its tolerance.
    """

    delivered_difference: Decimal
    delivered_impressions_difference: int
    media_cost_difference: Decimal
    reported_revenue_difference: Decimal | None
    buyer_spend_difference: Decimal | None
    current_margin: Decimal
    margin_difference: Decimal
    changed: bool
    billable_difference: Decimal | None = None
    billing_difference: Decimal | None = None
