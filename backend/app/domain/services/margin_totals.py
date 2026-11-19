from collections.abc import Iterable
from decimal import Decimal

from app.domain.value_objects.margin import FlightMargin, FlightStatus, MarginTotals

_ZERO = Decimal("0.00")


def _volumes_in_one_metric(
    metrics: set[str], contracted: int, delivered: Decimal
) -> tuple[str | None, int | None, Decimal | None]:
    """The metric and the volumes of a total. Two metrics cannot be added, so then all three are None."""
    if len(metrics) > 1:
        return None, None, None
    return (next(iter(metrics)) if metrics else None), contracted, delivered


def total_flights(flights: Iterable[FlightMargin]) -> MarginTotals:
    """A line's total: the exact sum of its flights' already rounded amounts, with no further rounding."""
    revenue = media_cost = rebate = platform_cost = margin = contracted_revenue = _ZERO
    provisional = False
    counted = below_cost = not_started = zero_sale = delivered_impressions = contracted = 0
    delivered = Decimal(0)
    metrics: set[str] = set()
    for flight in flights:
        if flight.delivery_metric is not None:
            metrics.add(flight.delivery_metric)
        if flight.status is FlightStatus.NOT_STARTED:
            not_started += 1
            continue
        assert flight.revenue is not None and flight.media_cost is not None
        assert flight.rebate is not None and flight.platform_cost is not None and flight.margin is not None
        assert flight.contracted_revenue is not None
        assert flight.delivered_impressions is not None and flight.contracted_impressions is not None
        assert flight.delivered is not None
        delivered_impressions += flight.delivered_impressions
        delivered += flight.delivered
        contracted += flight.contracted_impressions
        revenue += flight.revenue
        contracted_revenue += flight.contracted_revenue
        media_cost += flight.media_cost
        rebate += flight.rebate
        platform_cost += flight.platform_cost
        margin += flight.margin
        provisional = provisional or flight.provisional
        below_cost += flight.below_cost
        zero_sale += flight.zero_sale
        counted += 1
    metric, contracted_total, delivered_total = _volumes_in_one_metric(metrics, contracted, delivered)
    return MarginTotals(
        revenue, media_cost, rebate, platform_cost, margin, provisional, counted, below_cost, not_started, zero_sale,
        contracted_revenue, delivered_impressions, contracted_total, delivered_total, metric,
    )


def total_lines(lines: Iterable[MarginTotals]) -> MarginTotals:
    """A campaign's total: the exact sum of its lines' totals."""
    revenue = media_cost = rebate = platform_cost = margin = contracted_revenue = _ZERO
    provisional = False
    counted = below_cost = not_started = zero_sale = delivered_impressions = contracted = 0
    delivered = Decimal(0)
    metrics: set[str] = set()
    for line in lines:
        if line.delivery_metric is not None:
            metrics.add(line.delivery_metric)
        revenue += line.revenue
        contracted_revenue += line.contracted_revenue
        delivered_impressions += line.delivered_impressions
        if line.delivered is not None and line.contracted_impressions is not None:
            delivered += line.delivered
            contracted += line.contracted_impressions
        media_cost += line.media_cost
        rebate += line.rebate
        platform_cost += line.platform_cost
        margin += line.margin
        provisional = provisional or line.provisional
        counted += line.flights_counted
        below_cost += line.below_cost_count
        zero_sale += line.zero_sale_count
        not_started += line.not_started_count
    metric, contracted_total, delivered_total = _volumes_in_one_metric(metrics, contracted, delivered)
    return MarginTotals(
        revenue, media_cost, rebate, platform_cost, margin, provisional, counted, below_cost, not_started, zero_sale,
        contracted_revenue, delivered_impressions, contracted_total, delivered_total, metric,
    )
