from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.value_objects.margin import FlightEconomics, FlightMargin, FlightStatus

_CENT = Decimal("0.01")
_THOUSAND = Decimal(1000)


def round_amount(amount: Decimal) -> Decimal:
    """Two decimals, half up. The only rounding in the margin: applied once to each amount of a flight."""
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


def flight_revenue(contracted_impressions: int, sale_cpm: Decimal) -> Decimal:
    """The revenue of a whole flight: contracted volume times the line's CPM, rounded once."""
    return round_amount(Decimal(contracted_impressions) / _THOUSAND * sale_cpm)


def flight_status(flight: FlightEconomics, as_of: date) -> FlightStatus:
    """`as_of` is D-1, the last day counted: a flight ending on it is closed, one starting after it has not begun."""
    if flight.flight_start > as_of:
        return FlightStatus.NOT_STARTED
    if flight.flight_end <= as_of:
        return FlightStatus.CLOSED
    return FlightStatus.RUNNING


def calculate_flight_margin(flight: FlightEconomics, as_of: date) -> FlightMargin:
    """The margin of one flight as of D-1. Revenue never reads the delivered volume.

    A running flight pro-rates revenue and rebate by elapsed contract days of its own window; media cost and
    platform cost come from what was delivered and are not pro-rated.
    """
    status = flight_status(flight, as_of)
    if status is FlightStatus.NOT_STARTED:
        return FlightMargin(status, None, None, None, None, None, provisional=False, below_cost=False)

    full_revenue = Decimal(flight.contracted_impressions) / _THOUSAND * flight.sale_cpm
    full_rebate = flight.rebate_amount
    if status is FlightStatus.RUNNING:
        elapsed_days = (as_of - flight.flight_start).days + 1
        full_revenue = full_revenue * elapsed_days / flight.total_days
        full_rebate = full_rebate * elapsed_days / flight.total_days

    contracted_revenue = flight_revenue(flight.contracted_impressions, flight.sale_cpm)
    accrued_days = (min(as_of, flight.flight_end) - flight.flight_start).days + 1
    # A closed flight accrues all of its sale, so its revenue is the contracted revenue, rounded once.
    revenue = contracted_revenue if status is FlightStatus.CLOSED else round_amount(full_revenue)
    media_cost = round_amount(flight.media_cost)
    rebate = round_amount(full_rebate)
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
    )
