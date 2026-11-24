from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.value_objects.margin import FlightEconomics, FlightMargin, FlightStatus
from app.domain.value_objects.priced_flight import FlightFacts
from app.domain.value_objects.volume_commitment import VolumeCommitment

_CENT = Decimal("0.01")
_THOUSAND = Decimal(1000)
# How far the gross of a target flight may be from the buyer's spend, as a share of that spend, before it is flagged.
# Compared on rounded amounts: a spend of 5,000.00 € tolerates a gross from 4,950.00 € to 5,050.00 €.
GROSS_TOLERANCE = Decimal("0.01")


def round_amount(amount: Decimal) -> Decimal:
    """Two decimals, half up. The only rounding in the margin: applied once to each amount of a flight."""
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


def flight_revenue(contracted_impressions: int, sale_cpm: Decimal) -> Decimal:
    """The revenue of a whole flight: contracted volume times the line's CPM, rounded once."""
    return round_amount(Decimal(contracted_impressions) / _THOUSAND * sale_cpm)


def gross_revenue(delivered_impressions: int, sale_cpm: Decimal) -> Decimal:
    """What the served impressions are worth at the line's CPM, rounded once: the gross of a target flight."""
    return round_amount(Decimal(delivered_impressions) / _THOUSAND * sale_cpm)


def rebate_base(facts: FlightFacts) -> Decimal:
    """The amount the rebate is a percentage of: the sale of a committed flight, the served gross of a target one.

    The rebate engine, the counters and the frozen positions advance by it without knowing which it is.
    """
    if facts.volume_commitment is VolumeCommitment.TARGET:
        return gross_revenue(facts.delivered_impressions, facts.sale_cpm)
    return flight_revenue(facts.contracted_impressions, facts.sale_cpm)


def _gross_differs_from_buyer_spend(gross: Decimal, buyer_spend: Decimal) -> bool:
    spend = round_amount(buyer_spend)
    if spend == 0:
        return gross != 0
    return abs(gross - spend) > spend * GROSS_TOLERANCE


def flight_status(flight: FlightEconomics, as_of: date) -> FlightStatus:
    """`as_of` is D-1, the last day counted: a flight ending on it is closed, one starting after it has not begun."""
    if flight.flight_start > as_of:
        return FlightStatus.NOT_STARTED
    if flight.flight_end <= as_of:
        return FlightStatus.CLOSED
    return FlightStatus.RUNNING


def calculate_flight_margin(flight: FlightEconomics, as_of: date) -> FlightMargin:
    """The margin of one flight as of D-1. The revenue of a committed flight never reads the delivered volume.

    A committed flight earns on the contracted volume, in the unit of the metric (300,000 OTS at 5.00 € earn
    1,500.00 €). A target flight earns the revenue its DSP reports inside its window, and has a gross, its served
    impressions times the CPM, that its rebate was computed on. The platform cost is on the real delivered impressions,
    never on OTS.

    A running committed flight pro-rates revenue and rebate by elapsed contract days of its own window; a running
    target flight is not pro-rated, since what it reports is already what it earned to date. Media cost and platform
    cost come from what was delivered and are not pro-rated.
    """
    status = flight_status(flight, as_of)
    if status is FlightStatus.NOT_STARTED:
        return FlightMargin(
            status, None, None, None, None, None, provisional=False, below_cost=False,
            delivery_metric=flight.delivery_metric, volume_commitment=flight.volume_commitment,
        )

    contracted_revenue = flight_revenue(flight.contracted_impressions, flight.sale_cpm)
    accrued_days = (min(as_of, flight.flight_end) - flight.flight_start).days + 1
    gross: Decimal | None = None
    gross_differs = False
    if flight.volume_commitment is VolumeCommitment.TARGET:
        revenue = round_amount(flight.reported_revenue)
        rebate = round_amount(flight.rebate_amount)
        gross = gross_revenue(flight.delivered_impressions, flight.sale_cpm)
        gross_differs = _gross_differs_from_buyer_spend(gross, flight.buyer_spend)
    else:
        full_revenue = Decimal(flight.contracted_impressions) / _THOUSAND * flight.sale_cpm
        full_rebate = flight.rebate_amount
        if status is FlightStatus.RUNNING:
            elapsed_days = (as_of - flight.flight_start).days + 1
            full_revenue = full_revenue * elapsed_days / flight.total_days
            full_rebate = full_rebate * elapsed_days / flight.total_days
        # A closed flight accrues all of its sale, so its revenue is the contracted revenue, rounded once.
        revenue = contracted_revenue if status is FlightStatus.CLOSED else round_amount(full_revenue)
        rebate = round_amount(full_rebate)
    media_cost = round_amount(flight.media_cost)
    platform_cost = round_amount(Decimal(flight.delivered_impressions) / _THOUSAND * flight.platform_rate)
    margin = revenue - media_cost - rebate - platform_cost
    return FlightMargin(
        status=status,
        revenue=revenue,
        media_cost=media_cost,
        rebate=rebate,
        platform_cost=platform_cost,
        margin=margin,
        provisional=status is FlightStatus.RUNNING,
        # Margen negativo: the final margin, made of the rounded amounts, is below zero.
        below_cost=margin < 0,
        zero_sale=flight.sale_cpm == 0,
        contracted_revenue=contracted_revenue,
        accrued_days=accrued_days,
        window_days=flight.total_days,
        delivered_impressions=flight.delivered_impressions,
        contracted_impressions=flight.contracted_impressions,
        delivered=flight.delivered,
        delivery_metric=flight.delivery_metric,
        volume_commitment=flight.volume_commitment,
        gross_revenue=gross,
        gross_differs_from_buyer_spend=gross_differs,
        data_cost_reported=flight.data_cost > 0,
    )
