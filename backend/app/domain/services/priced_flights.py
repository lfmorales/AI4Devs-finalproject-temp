from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal

from app.domain.services.flight_margin import calculate_flight_margin, flight_revenue
from app.domain.services.platform_rate import resolve_platform_rate
from app.domain.services.rebate_engine import calculate_rebates
from app.domain.value_objects.margin import FlightEconomics
from app.domain.value_objects.priced_flight import FlightFacts, PlatformRates, PricedFlight
from app.domain.value_objects.rebate import CounterKey, RebateFlight, RebateSchedule


def price_flights(
    schedules: Sequence[RebateSchedule],
    platform_rates: PlatformRates,
    flights: Sequence[FlightFacts],
    as_of: date,
    opening_positions: Mapping[CounterKey, Decimal] | None = None,
) -> tuple[PricedFlight, ...]:
    """Price flights as of D-1: the rebate engine, the platform rate and the margin, in application order.

    The one function behind both the closing of a month, which writes its output, and the reads of a running
    or pending-close flight, which only return it, so the two cannot diverge. Flights that have not started
    are left out.
    """
    rebates = {
        rebate.flight_id: rebate
        for rebate in calculate_rebates(
            schedules,
            [
                RebateFlight(
                    flight_id=facts.flight_id, flight_start=facts.flight_start, flight_end=facts.flight_end,
                    group_id=facts.group_id, agency_id=facts.agency_id, channel=facts.channel, scope=facts.scope,
                    revenue=flight_revenue(facts.contracted_impressions, facts.sale_cpm),
                )
                for facts in flights
            ],
            as_of,
            opening_positions,
        )
    }
    priced: list[PricedFlight] = []
    for facts in sorted(flights, key=lambda f: (f.flight_start, f.flight_id)):
        rebate = rebates.get(facts.flight_id)
        if rebate is None:
            continue
        platform = resolve_platform_rate(
            system=platform_rates.system,
            line=platform_rates.by_line.get(facts.campaign_line_id),
            agency=platform_rates.by_agency.get(facts.agency_id),
            campaign_type=platform_rates.by_campaign_type.get(facts.campaign_type_id),
        )
        margin = calculate_flight_margin(
            FlightEconomics(
                flight_start=facts.flight_start, flight_end=facts.flight_end,
                contracted_impressions=facts.contracted_impressions, sale_cpm=facts.sale_cpm,
                delivered_impressions=facts.delivered_impressions, media_cost=facts.media_cost,
                rebate_amount=rebate.rebate, platform_rate=platform.rate,
            ),
            as_of,
        )
        priced.append(PricedFlight(facts, rebate, platform, margin))
    return tuple(priced)
