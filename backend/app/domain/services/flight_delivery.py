from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from app.domain.value_objects.delivery import DailyDelivery
from app.domain.value_objects.margin import WindowDelivery


def deliveries_in_window(
    deliveries: Iterable[DailyDelivery], campaign_line_id: int, flight_start: date, flight_end: date
) -> WindowDelivery:
    """Sum one line's delivery dated from `flight_start` to `flight_end`, both included.

    A delivery stored outside every flight of its line, or belonging to another line, counts toward nothing.
    The media cost is summed as stored, without rounding: rounding is the margin's job, once per amount.
    """
    impressions = 0
    media_cost = Decimal(0)
    for delivery in deliveries:
        if delivery.campaign_line_id == campaign_line_id and flight_start <= delivery.delivery_date <= flight_end:
            impressions += delivery.impressions
            media_cost += delivery.media_cost
    return WindowDelivery(impressions=impressions, media_cost=media_cost)
