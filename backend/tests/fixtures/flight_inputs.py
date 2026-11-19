"""Builders for the flight inputs of the margin: the delivery metric and the delivered volume have defaults here, not in the domain.

Left out, a flight counts in impressions and `delivered` is its `delivered_impressions`. Production code never relies on
that: it always reads both from the stored delivery.
"""

from datetime import date
from decimal import Decimal

from app.domain.value_objects.margin import FlightEconomics
from app.domain.value_objects.priced_flight import FlightFacts


def flight_economics(
    *,
    flight_start: date,
    flight_end: date,
    contracted_impressions: int,
    sale_cpm: Decimal,
    delivered_impressions: int,
    media_cost: Decimal,
    rebate_amount: Decimal,
    platform_rate: Decimal,
    delivery_metric: str = "impressions",
    delivered: Decimal | None = None,
) -> FlightEconomics:
    return FlightEconomics(
        flight_start=flight_start, flight_end=flight_end, contracted_impressions=contracted_impressions,
        sale_cpm=sale_cpm, delivered_impressions=delivered_impressions, media_cost=media_cost,
        rebate_amount=rebate_amount, platform_rate=platform_rate, delivery_metric=delivery_metric,
        delivered=Decimal(delivered_impressions) if delivered is None else delivered,
    )


def flight_facts(
    *,
    flight_id: int,
    campaign_line_id: int,
    campaign_id: int,
    flight_start: date,
    flight_end: date,
    group_id: int,
    agency_id: int,
    campaign_type_id: int,
    channel: str,
    channel_id: int,
    scope: str,
    contracted_impressions: int,
    sale_cpm: Decimal,
    delivered_impressions: int,
    media_cost: Decimal,
    delivery_metric: str = "impressions",
    delivered: Decimal | None = None,
) -> FlightFacts:
    return FlightFacts(
        flight_id=flight_id, campaign_line_id=campaign_line_id, campaign_id=campaign_id, flight_start=flight_start,
        flight_end=flight_end, group_id=group_id, agency_id=agency_id, campaign_type_id=campaign_type_id,
        channel=channel, channel_id=channel_id, scope=scope, contracted_impressions=contracted_impressions,
        sale_cpm=sale_cpm, delivered_impressions=delivered_impressions, media_cost=media_cost,
        delivery_metric=delivery_metric,
        delivered=Decimal(delivered_impressions) if delivered is None else delivered,
    )
