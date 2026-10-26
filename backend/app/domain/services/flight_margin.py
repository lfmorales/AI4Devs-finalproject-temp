from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.value_objects.margin import FlightEconomics, FlightMargin, FlightStatus

_CENT = Decimal("0.01")
_THOUSAND = Decimal(1000)


def round_amount(amount: Decimal) -> Decimal:
    """Two decimals, half up. The only rounding in the margin: applied once to each amount of a flight."""
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


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

    revenue = round_amount(full_revenue)
    media_cost = round_amount(flight.media_cost)
    rebate = round_amount(full_rebate)
    platform_cost = round_amount(Decimal(flight.delivered_impressions) / _THOUSAND * flight.platform_rate)
    return FlightMargin(
        status=status,
        revenue=revenue,
        media_cost=media_cost,
        rebate=rebate,
        platform_cost=platform_cost,
        margin=revenue - media_cost - rebate - platform_cost,
        provisional=status is FlightStatus.RUNNING,
        below_cost=media_cost > revenue,
    )
