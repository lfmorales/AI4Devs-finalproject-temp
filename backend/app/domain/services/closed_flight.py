"""A closed flight: the snapshot its closing freezes, its margin read back from it, and the check of its delivery."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.services.flight_margin import round_amount
from app.domain.value_objects.closed_flight import ClosedDeliveryCheck, ClosedFlightSnapshot
from app.domain.value_objects.margin import FlightMargin, FlightStatus, WindowDelivery
from app.domain.value_objects.priced_flight import PricedFlight
from app.domain.value_objects.volume_commitment import VolumeCommitment

# A closed flight is flagged when the margin its current delivery would give is this far from its frozen margin, or
# more, in either direction...
MARGIN_CHANGE_TOLERANCE = Decimal("1.00")
# ...or when its current delivered volume is this share of its frozen volume away from it, or more.
DELIVERED_CHANGE_TOLERANCE = Decimal("0.01")
_THOUSAND = Decimal(1000)
_TEN_THOUSANDTH = Decimal("0.0001")


def snapshot_of(priced: PricedFlight) -> ClosedFlightSnapshot:
    """The snapshot of a flight the closing priced: the amounts it showed and the delivery they were computed on.

    The closing and the pending-close read price with the same function, so the snapshot holds, by construction, the
    figures the pending-close read showed. Only a closed flight has one.
    """
    margin, facts = priced.margin, priced.facts
    if (
        margin.status is not FlightStatus.CLOSED
        or margin.revenue is None
        or margin.contracted_revenue is None
        or margin.media_cost is None
        or margin.rebate is None
        or margin.platform_cost is None
        or margin.margin is None
    ):
        raise ValueError(f"flight {facts.flight_id} is not closed, so it has no snapshot")
    return ClosedFlightSnapshot(
        revenue=margin.revenue,
        contracted_revenue=margin.contracted_revenue,
        media_cost=margin.media_cost,
        rebate=margin.rebate,
        platform_cost=margin.platform_cost,
        margin=margin.margin,
        gross_revenue=margin.gross_revenue,
        delivered_impressions=facts.delivered_impressions,
        delivered=facts.delivered,
        window_media_cost=facts.media_cost,
        window_reported_revenue=facts.reported_revenue,
        window_buyer_spend=facts.buyer_spend,
        window_data_cost=facts.data_cost,
        gross_differs_from_buyer_spend=margin.gross_differs_from_buyer_spend,
        data_cost_reported=margin.data_cost_reported,
        delivery_metric=facts.delivery_metric,
        sale_cpm=facts.sale_cpm,
        contracted_impressions=facts.contracted_impressions,
        volume_commitment=facts.volume_commitment,
    )


def margin_from_snapshot(snapshot: ClosedFlightSnapshot, flight_start: date, flight_end: date) -> FlightMargin:
    """The margin of a closed flight, as its closing froze it: nothing is computed again, nothing is rounded.

    A closed flight has accrued every day of its window, so both counts are the window's, and it is never provisional.
    Below cost and zero sale are read from the frozen margin and the frozen sale CPM, not from today's line.
    """
    window_days = (flight_end - flight_start).days + 1
    return FlightMargin(
        status=FlightStatus.CLOSED,
        revenue=snapshot.revenue,
        media_cost=snapshot.media_cost,
        rebate=snapshot.rebate,
        platform_cost=snapshot.platform_cost,
        margin=snapshot.margin,
        provisional=False,
        below_cost=snapshot.margin < 0,
        zero_sale=snapshot.sale_cpm == 0,
        contracted_revenue=snapshot.contracted_revenue,
        accrued_days=window_days,
        window_days=window_days,
        delivered_impressions=snapshot.delivered_impressions,
        contracted_impressions=snapshot.contracted_impressions,
        delivered=snapshot.delivered,
        delivery_metric=snapshot.delivery_metric,
        volume_commitment=snapshot.volume_commitment,
        gross_revenue=snapshot.gross_revenue,
        gross_differs_from_buyer_spend=snapshot.gross_differs_from_buyer_spend,
        data_cost_reported=snapshot.data_cost_reported,
    )


def check_closed_delivery(
    snapshot: ClosedFlightSnapshot, platform_rate: Decimal, current: WindowDelivery
) -> ClosedDeliveryCheck:
    """Compare a closed flight with the delivery stored now in its window; no figure of the flight changes.

    `platform_rate` is the rate its closing froze, and `current.delivered` is summed in the snapshot's metric. Nothing
    is resolved again: the current margin keeps the closing's rebate and, for a committed flight, its revenue.
    """
    is_target = snapshot.volume_commitment is VolumeCommitment.TARGET
    current_revenue = round_amount(current.reported_revenue) if is_target else snapshot.revenue
    current_media_cost = round_amount(current.media_cost)
    current_platform_cost = round_amount(Decimal(current.impressions) / _THOUSAND * platform_rate)
    current_margin = current_revenue - current_media_cost - snapshot.rebate - current_platform_cost
    margin_difference = current_margin - snapshot.margin
    delivered_difference = current.delivered - snapshot.delivered
    return ClosedDeliveryCheck(
        delivered_difference=delivered_difference.quantize(_TEN_THOUSANDTH, rounding=ROUND_HALF_UP),
        delivered_impressions_difference=current.impressions - snapshot.delivered_impressions,
        media_cost_difference=current_media_cost - snapshot.media_cost,
        reported_revenue_difference=(
            round_amount(current.reported_revenue) - round_amount(snapshot.window_reported_revenue) if is_target else None
        ),
        buyer_spend_difference=(
            round_amount(current.buyer_spend) - round_amount(snapshot.window_buyer_spend) if is_target else None
        ),
        current_margin=current_margin,
        margin_difference=margin_difference,
        changed=(
            abs(margin_difference) >= MARGIN_CHANGE_TOLERANCE
            or _delivered_moved(snapshot.delivered, current.delivered)
        ),
    )


def _delivered_moved(frozen: Decimal, current: Decimal) -> bool:
    """A frozen volume of zero is exceeded by any current volume that is not zero."""
    if frozen == 0:
        return current != 0
    return abs(current - frozen) >= frozen * DELIVERED_CHANGE_TOLERANCE
