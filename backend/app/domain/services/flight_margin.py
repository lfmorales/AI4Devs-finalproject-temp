from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.value_objects.billing import Billing, BillingAdjustment, BillingBasis
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
    """The contracted sale of a whole flight: contracted volume times the line's CPM, rounded once.

    It is the flight's `contracted_revenue`, not its revenue: a committed flight earns its billing.
    """
    return round_amount(Decimal(contracted_impressions) / _THOUSAND * sale_cpm)


def committed_billing(
    *,
    contracted: int,
    carryover: int,
    carryover_billable: bool,
    delivered: Decimal,
    sale_cpm: Decimal,
    adjustment: BillingAdjustment | None,
) -> Billing:
    """What a committed flight bills: the lesser of its delivered volume and its cap, times the CPM, rounded once.

    The cap is the contracted volume, plus the carry-over when the carry-over is billable. An adjustment in force
    replaces the rule: `delivered` bills the delivered volume with no cap, `contracted` the cap, `custom` its amount,
    and `minimum` is the rule itself. Every volume is in the unit of the delivery metric; `delivered` keeps its decimals.
    """
    cap = Decimal(contracted + (carryover if carryover_billable else 0))
    basis = BillingBasis.MINIMUM if adjustment is None else adjustment.basis
    if basis is BillingBasis.CUSTOM:
        assert adjustment is not None and adjustment.amount is not None
        return Billing(billable=None, amount=adjustment.amount, basis=basis)
    if basis is BillingBasis.DELIVERED:
        billable = delivered
    elif basis is BillingBasis.CONTRACTED:
        billable = cap
    else:
        billable = min(delivered, cap)
    return Billing(billable=billable, amount=round_amount(billable / _THOUSAND * sale_cpm), basis=basis)


def gross_revenue(delivered_impressions: int, sale_cpm: Decimal) -> Decimal:
    """What the served impressions are worth at the line's CPM, rounded once: the gross of a target flight."""
    return round_amount(Decimal(delivered_impressions) / _THOUSAND * sale_cpm)


def rebate_base(facts: FlightFacts) -> Decimal:
    """The amount the rebate is a percentage of: the billing of a committed flight, to date while it runs, and the
    served gross of a target one.

    The rebate engine, the counters and the frozen positions advance by it without knowing which it is.
    """
    if facts.volume_commitment is VolumeCommitment.TARGET:
        return gross_revenue(facts.delivered_impressions, facts.sale_cpm)
    return committed_billing(
        contracted=facts.contracted_impressions, carryover=facts.carryover,
        carryover_billable=facts.carryover_billable, delivered=facts.delivered, sale_cpm=facts.sale_cpm,
        adjustment=facts.adjustment,
    ).amount


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
    """The margin of one flight as of D-1.

    A committed flight earns its billing (`committed_billing`), in the unit of the metric: 280,000.50 OTS delivered of
    300,000 contracted at 5.00 € bill 1,400.00 €. A target flight earns the revenue its DSP reports inside its window,
    and has a gross, its served impressions times the CPM, that its rebate was computed on. The platform cost is on the
    real delivered impressions, never on OTS.

    Nothing is pro-rated by elapsed days: a running committed flight earns its billing to date and its rebate is the
    engine's, computed on that billing; a running target flight earns what was reported to date. Media cost and
    platform cost come from what was delivered.
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
    billable: Decimal | None = None
    if flight.volume_commitment is VolumeCommitment.TARGET:
        revenue = round_amount(flight.reported_revenue)
        billing_basis = BillingBasis.REPORTED
        # What was served, at the CPM. A closed flight is never priced again: it is read from its snapshot.
        gross = gross_revenue(flight.delivered_impressions, flight.sale_cpm)
        gross_differs = _gross_differs_from_buyer_spend(gross, flight.buyer_spend)
    else:
        billing = committed_billing(
            contracted=flight.contracted_impressions, carryover=flight.carryover,
            carryover_billable=flight.carryover_billable, delivered=flight.delivered, sale_cpm=flight.sale_cpm,
            adjustment=flight.adjustment,
        )
        revenue, billable, billing_basis = billing.amount, billing.billable, billing.basis
    rebate = round_amount(flight.rebate_amount)
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
        billable=billable,
        billing_basis=billing_basis,
    )
