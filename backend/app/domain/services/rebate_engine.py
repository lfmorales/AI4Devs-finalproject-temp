from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from app.domain.exceptions import RebateRuleError
from app.domain.services.rebate_brackets import apply_brackets
from app.domain.services.rebate_ladder import resolve_rebate_schedule
from app.domain.value_objects.rebate import CounterKey, FlightRebate, RebateFlight, RebateSchedule, ResolvedRebate


def _order(flight: RebateFlight) -> tuple[date, int]:
    return flight.flight_start, flight.flight_id


def _counter_key(flight: RebateFlight, resolved: ResolvedRebate) -> CounterKey:
    """The agency slot is set only when an agency exception priced the flight; the year is the year of its start."""
    agency_id = flight.agency_id if resolved.agency_exception else None
    return CounterKey(flight.group_id, agency_id, flight.channel, flight.flight_start.year)


def _price(
    flight: RebateFlight, resolved: ResolvedRebate, counter: CounterKey, position_before: Decimal, advances: bool
) -> FlightRebate:
    brackets = resolved.schedule.brackets if resolved.schedule is not None else ()
    breakdown = apply_brackets(brackets, position_before, flight.revenue) if brackets else None
    return FlightRebate(
        flight_id=flight.flight_id,
        counter=counter,
        step=resolved.step,
        agency_exception=resolved.agency_exception,
        source_year=resolved.source_year,
        zero_reason=resolved.zero_reason,
        schedule_id=resolved.schedule.schedule_id if resolved.schedule is not None else None,
        effective_rate=breakdown.effective_rate if breakdown is not None else Decimal(0),
        position_before=position_before,
        position_after=position_before + flight.revenue if advances else position_before,
        charges=breakdown.charges if breakdown is not None else (),
        rebate=breakdown.rebate if breakdown is not None else Decimal(0),
    )


def calculate_rebates(
    schedules: Sequence[RebateSchedule], flights: Sequence[RebateFlight], as_of: date
) -> tuple[FlightRebate, ...]:
    """Price every started flight against its annual counter and return the results in application order.

    A flight is closed when `flight_end <= as_of`, running when it started but has not ended, and a flight
    that has not started is left out. The closed flights of a counter are applied in order of `flight_start`,
    ties broken by flight id, so the result does not depend on the order of the input. A running flight reads
    the position after every closed flight of its counter, charges its full revenue from there, and does not
    advance the counter; the margin calculation pro-rates the rebate.
    """
    if len({flight.flight_id for flight in flights}) != len(flights):
        raise RebateRuleError("duplicate_flight_id", "a flight id appears twice")

    started = sorted((flight for flight in flights if flight.flight_start <= as_of), key=_order)
    resolutions = {flight.flight_id: resolve_rebate_schedule(schedules, flight) for flight in started}
    counters = {flight.flight_id: _counter_key(flight, resolutions[flight.flight_id]) for flight in started}

    positions: dict[CounterKey, Decimal] = {}
    results: dict[int, FlightRebate] = {}
    for flight in (f for f in started if f.flight_end <= as_of):
        counter = counters[flight.flight_id]
        before = positions.get(counter, Decimal(0))
        results[flight.flight_id] = _price(flight, resolutions[flight.flight_id], counter, before, advances=True)
        positions[counter] = before + flight.revenue
    for flight in (f for f in started if f.flight_end > as_of):
        counter = counters[flight.flight_id]
        before = positions.get(counter, Decimal(0))
        results[flight.flight_id] = _price(flight, resolutions[flight.flight_id], counter, before, advances=False)
    return tuple(results[flight.flight_id] for flight in started)
