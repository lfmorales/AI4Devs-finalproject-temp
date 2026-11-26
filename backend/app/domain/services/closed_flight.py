"""A closed flight: the snapshot its closing freezes, and its margin read back from that snapshot."""

from datetime import date

from app.domain.value_objects.closed_flight import ClosedFlightSnapshot
from app.domain.value_objects.margin import FlightMargin, FlightStatus
from app.domain.value_objects.priced_flight import PricedFlight


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
