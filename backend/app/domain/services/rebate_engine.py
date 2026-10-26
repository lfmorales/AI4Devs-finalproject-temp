from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from app.domain.exceptions import RebateRuleError
from app.domain.services.rebate_brackets import apply_brackets
from app.domain.services.rebate_ladder import resolve_rebate_schedule
from app.domain.value_objects.rebate import CounterKey, FlightRebate, RebateFlight, RebateSchedule


def calculate_rebates(
    schedules: Sequence[RebateSchedule], flights: Sequence[RebateFlight], as_of: date
) -> tuple[FlightRebate, ...]:
    """Price every flight against its annual counter and return the results in application order.

    A flight is closed when `flight_end <= as_of`. Closed flights of a counter are applied in order of
    `flight_start`, ties broken by flight id, so the result does not depend on the order of the input.
    """
    if len({flight.flight_id for flight in flights}) != len(flights):
        raise RebateRuleError("duplicate_flight_id", "a flight id appears twice")

    ordered = sorted(
        (flight for flight in flights if flight.flight_start <= as_of), key=lambda f: (f.flight_start, f.flight_id)
    )
    positions: dict[CounterKey, Decimal] = {}
    results: list[FlightRebate] = []
    for flight in ordered:
        if flight.flight_end > as_of:
            raise NotImplementedError("running flights are not calculated yet")
        resolved = resolve_rebate_schedule(schedules, flight)
        counter = CounterKey(flight.group_id, None, flight.channel, flight.flight_start.year)
        before = positions.get(counter, Decimal(0))
        brackets = resolved.schedule.brackets if resolved.schedule is not None else ()
        breakdown = apply_brackets(brackets, before, flight.revenue) if brackets else None
        positions[counter] = before + flight.revenue
        results.append(
            FlightRebate(
                flight_id=flight.flight_id,
                counter=counter,
                step=resolved.step,
                agency_exception=resolved.agency_exception,
                source_year=resolved.source_year,
                zero_reason=resolved.zero_reason,
                schedule_id=resolved.schedule.schedule_id if resolved.schedule is not None else None,
                effective_rate=breakdown.effective_rate if breakdown is not None else Decimal(0),
                position_before=before,
                position_after=before + flight.revenue,
                charges=breakdown.charges if breakdown is not None else (),
                rebate=breakdown.rebate if breakdown is not None else Decimal(0),
            )
        )
    return tuple(results)
