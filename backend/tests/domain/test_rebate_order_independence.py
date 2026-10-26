"""The result does not depend on the order of the input, across several counters, an exception and every state."""

import random
from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.domain.services.rebate_engine import calculate_rebates
from app.domain.value_objects.rebate import Bracket, CounterKey, LadderStep, RebateFlight, RebateSchedule
from tests.domain.test_rebate_engine import GROUP, TWO_BRACKETS, group_schedule, month_flight
from tests.domain.test_rebate_ladder import AGENCY

AS_OF = date(2026, 6, 10)
SHUFFLES = 25
SEED = 20261026


def _schedules() -> list[RebateSchedule]:
    other_group = RebateSchedule(7, GROUP + 1, None, None, None, date(2026, 1, 1), None, TWO_BRACKETS)
    exception = RebateSchedule(
        8, GROUP, AGENCY, None, None, date(2026, 1, 1), None, (Bracket(Decimal(0), None, Decimal("0.30")),)
    )
    return [group_schedule(), other_group, exception]


def _flights() -> list[RebateFlight]:
    other_agency = AGENCY + 1
    return [
        month_flight(1, 1, "60000"),
        month_flight(2, 2, "70000"),                                              # crosses 100,000 in the group
        replace(month_flight(3, 2, "50000", day=10), agency_id=other_agency),     # same counter, later in February
        replace(month_flight(4, 2, "50000", day=10), agency_id=other_agency),     # tie on flight_start with id 3
        month_flight(5, 3, "40000", channel="Deal"),
        replace(month_flight(6, 3, "90000"), group_id=GROUP + 1),
        replace(month_flight(7, 4, "30000"), group_id=GROUP + 1),
        month_flight(8, 3, "20000", channel="Deal"),
        month_flight(9, 4, "80000", channel="Directo"),                            # the exception agency, own counter
        replace(month_flight(10, 5, "1000"), group_id=GROUP + 2),                  # a group with no schedule
        replace(month_flight(11, 6, "30000"), flight_end=date(2026, 6, 28)),       # running on the 10th
        replace(month_flight(12, 6, "5000", day=5), flight_end=date(2026, 6, 9)),  # closed, starts after the running one
        month_flight(13, 9, "10000"),                                              # not started
    ]


def _exception_flights() -> list[RebateFlight]:
    # Flights 9 and 14 belong to the excepted agency; the others use the sibling agency.
    flights = _flights()
    flights = [replace(flight, agency_id=AGENCY + 1) if flight.flight_id not in (9, 14) else flight for flight in flights]
    flights.append(month_flight(14, 5, "15000"))
    return flights


def _expected():
    return calculate_rebates(_schedules(), _exception_flights(), AS_OF)


def test_the_scenario_really_uses_several_counters_an_exception_and_every_state():
    results = {result.flight_id: result for result in _expected()}

    assert {result.counter for result in results.values()} == {
        CounterKey(GROUP, None, "Directo", 2026),
        CounterKey(GROUP, None, "Deal", 2026),
        CounterKey(GROUP, AGENCY, "Directo", 2026),
        CounterKey(GROUP + 1, None, "Directo", 2026),
        CounterKey(GROUP + 2, None, "Directo", 2026),
    }
    assert results[9].counter == CounterKey(GROUP, AGENCY, "Directo", 2026)
    assert results[9].agency_exception is True
    assert results[10].step is LadderStep.EXPLICIT_ZERO
    assert 13 not in results
    assert results[11].position_after == results[11].position_before
    assert results[3].position_before == Decimal(130_000)  # 60,000 + 70,000, by date; id 3 before id 4
    assert results[4].position_before == Decimal(180_000)


def test_every_rotation_of_the_input_gives_the_same_result():
    flights = _exception_flights()
    expected = _expected()

    for offset in range(len(flights)):
        rotated = flights[offset:] + flights[:offset]
        assert calculate_rebates(_schedules(), rotated, AS_OF) == expected


def test_the_reversed_input_gives_the_same_result():
    assert calculate_rebates(_schedules(), list(reversed(_exception_flights())), AS_OF) == _expected()


def test_shuffled_inputs_give_the_same_result():
    flights = _exception_flights()
    expected = _expected()
    generator = random.Random(SEED)

    for _ in range(SHUFFLES):
        shuffled = flights[:]
        generator.shuffle(shuffled)
        assert calculate_rebates(_schedules(), shuffled, AS_OF) == expected


def test_the_order_of_the_schedules_does_not_matter_either():
    generator = random.Random(SEED)
    expected = _expected()

    for _ in range(SHUFFLES):
        schedules = _schedules()
        generator.shuffle(schedules)
        assert calculate_rebates(schedules, _exception_flights(), AS_OF) == expected
