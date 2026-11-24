from collections.abc import Iterable
from decimal import Decimal

from app.domain.value_objects.margin import FlightMargin, FlightStatus, MarginTotals
from app.domain.value_objects.volume_commitment import VolumeCommitment

_ZERO = Decimal("0.00")


def _one_commitment(commitments: set[VolumeCommitment], disagree: bool) -> VolumeCommitment | None:
    """The commitment shared by everything below, or None when two disagree or there is nothing below."""
    if disagree or len(commitments) != 1:
        return None
    return next(iter(commitments))


def _add_gross(total: Decimal | None, gross: Decimal | None) -> Decimal | None:
    """Only target flights have a gross; a total with none of them has none."""
    if gross is None:
        return total
    return gross if total is None else total + gross


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
    gross: Decimal | None = None
    gross_differs = data_cost = 0
    commitments: set[VolumeCommitment] = set()
    for flight in flights:
        if flight.delivery_metric is not None:
            metrics.add(flight.delivery_metric)
        # Known before the flight starts, like the metric.
        if flight.volume_commitment is not None:
            commitments.add(flight.volume_commitment)
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
        gross = _add_gross(gross, flight.gross_revenue)
        gross_differs += flight.gross_differs_from_buyer_spend
        data_cost += flight.data_cost_reported
        counted += 1
    metric, contracted_total, delivered_total = _volumes_in_one_metric(metrics, contracted, delivered)
    return MarginTotals(
        revenue, media_cost, rebate, platform_cost, margin, provisional, counted, below_cost, not_started, zero_sale,
        contracted_revenue, delivered_impressions, contracted_total, delivered_total, metric,
        gross_revenue=gross, gross_differs_count=gross_differs, data_cost_count=data_cost,
        volume_commitment=_one_commitment(commitments, disagree=False),
    )


def total_lines(lines: Iterable[MarginTotals]) -> MarginTotals:
    """A campaign's total: the exact sum of its lines' totals."""
    revenue = media_cost = rebate = platform_cost = margin = contracted_revenue = _ZERO
    provisional = False
    counted = below_cost = not_started = zero_sale = delivered_impressions = contracted = 0
    delivered = Decimal(0)
    metrics: set[str] = set()
    gross: Decimal | None = None
    gross_differs = data_cost = 0
    commitments: set[VolumeCommitment] = set()
    disagree = False
    for line in lines:
        if line.delivery_metric is not None:
            metrics.add(line.delivery_metric)
        # A total with flights below and no commitment is one whose flights disagree; with no flights it says nothing.
        if line.flights_counted + line.not_started_count > 0:
            if line.volume_commitment is None:
                disagree = True
            else:
                commitments.add(line.volume_commitment)
        gross = _add_gross(gross, line.gross_revenue)
        gross_differs += line.gross_differs_count
        data_cost += line.data_cost_count
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
        gross_revenue=gross, gross_differs_count=gross_differs, data_cost_count=data_cost,
        volume_commitment=_one_commitment(commitments, disagree),
    )
