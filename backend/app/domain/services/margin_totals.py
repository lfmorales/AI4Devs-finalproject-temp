from collections.abc import Iterable
from decimal import Decimal

from app.domain.value_objects.margin import FlightMargin, FlightStatus, MarginTotals

_ZERO = Decimal("0.00")


def total_flights(flights: Iterable[FlightMargin]) -> MarginTotals:
    """A line's total: the exact sum of its flights' already rounded amounts, with no further rounding."""
    revenue = media_cost = rebate = platform_cost = margin = _ZERO
    provisional = False
    counted = below_cost = not_started = zero_sale = 0
    for flight in flights:
        if flight.status is FlightStatus.NOT_STARTED:
            not_started += 1
            continue
        assert flight.revenue is not None and flight.media_cost is not None
        assert flight.rebate is not None and flight.platform_cost is not None and flight.margin is not None
        revenue += flight.revenue
        media_cost += flight.media_cost
        rebate += flight.rebate
        platform_cost += flight.platform_cost
        margin += flight.margin
        provisional = provisional or flight.provisional
        below_cost += flight.below_cost
        zero_sale += flight.zero_sale
        counted += 1
    return MarginTotals(revenue, media_cost, rebate, platform_cost, margin, provisional, counted, below_cost, not_started, zero_sale)


def total_lines(lines: Iterable[MarginTotals]) -> MarginTotals:
    """A campaign's total: the exact sum of its lines' totals."""
    revenue = media_cost = rebate = platform_cost = margin = _ZERO
    provisional = False
    counted = below_cost = not_started = zero_sale = 0
    for line in lines:
        revenue += line.revenue
        media_cost += line.media_cost
        rebate += line.rebate
        platform_cost += line.platform_cost
        margin += line.margin
        provisional = provisional or line.provisional
        counted += line.flights_counted
        below_cost += line.below_cost_count
        zero_sale += line.zero_sale_count
        not_started += line.not_started_count
    return MarginTotals(revenue, media_cost, rebate, platform_cost, margin, provisional, counted, below_cost, not_started, zero_sale)
