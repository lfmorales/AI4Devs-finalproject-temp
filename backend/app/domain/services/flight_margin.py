from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.value_objects.margin import FlightEconomics, FlightMargin, FlightStatus

_CENT = Decimal("0.01")
_THOUSAND = Decimal(1000)


def round_amount(amount: Decimal) -> Decimal:
    """Two decimals, half up. The only rounding in the margin: applied once to each amount of a flight."""
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


def calculate_flight_margin(flight: FlightEconomics, as_of: date) -> FlightMargin:
    """The margin of one flight as of D-1. Revenue never reads the delivered volume."""
    if flight.flight_end > as_of:
        raise NotImplementedError("only closed flights are calculated so far")
    revenue = round_amount(Decimal(flight.contracted_impressions) / _THOUSAND * flight.sale_cpm)
    media_cost = round_amount(flight.media_cost)
    rebate = round_amount(flight.rebate_amount)
    platform_cost = round_amount(Decimal(flight.delivered_impressions) / _THOUSAND * flight.platform_rate)
    return FlightMargin(
        status=FlightStatus.CLOSED,
        revenue=revenue,
        media_cost=media_cost,
        rebate=rebate,
        platform_cost=platform_cost,
        margin=revenue - media_cost - rebate - platform_cost,
        provisional=False,
        below_cost=False,
    )
