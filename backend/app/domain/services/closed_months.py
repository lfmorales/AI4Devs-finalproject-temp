from collections.abc import Collection

from app.domain.value_objects.delivery import DeliveryDateRange


def days_in_closed_months(window: DeliveryDateRange, closed_months: Collection[tuple[int, int]]) -> int:
    """How many calendar days of `window` fall in a closed month, given as (year, month).

    Only counted: an ingestion still replaces those days, and a closed flight is checked against them.
    """
    closed = set(closed_months)
    return sum(1 for day in window.days() if (day.year, day.month) in closed)
