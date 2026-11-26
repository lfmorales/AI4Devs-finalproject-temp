from dataclasses import dataclass
from decimal import Decimal

from app.domain.value_objects.volume_commitment import VolumeCommitment

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
