"""The engine applies a counter's closed flights in chronological order and charges each its marginal brackets."""

import itertools
from datetime import date
from decimal import Decimal

from app.domain.services.rebate_engine import calculate_rebates
from app.domain.value_objects.rebate import Bracket, LadderStep, RebateFlight, RebateSchedule
from tests.domain.test_rebate_ladder import AGENCY, GROUP

AS_OF = date(2026, 12, 31)
TWO_BRACKETS = (
    Bracket(Decimal(0), Decimal(100_000), Decimal("0.15")),
    Bracket(Decimal(100_000), None, Decimal("0.20")),
)
THREE_BRACKETS = (
    Bracket(Decimal(0), Decimal(100_000), Decimal("0.15")),
    Bracket(Decimal(100_000), Decimal(500_000), Decimal("0.20")),
    Bracket(Decimal(500_000), None, Decimal("0.25")),
)


def group_schedule(brackets: tuple[Bracket, ...] = TWO_BRACKETS) -> RebateSchedule:
    return RebateSchedule(
        schedule_id=1, group_id=GROUP, agency_id=None, channel=None, scope=None,
        valid_from=date(2026, 1, 1), valid_to=date(2026, 12, 31), brackets=brackets,
    )


def month_flight(flight_id: int, month: int, revenue: str, *, day: int = 1, channel: str = "Directo") -> RebateFlight:
    return RebateFlight(
        flight_id=flight_id,
        flight_start=date(2026, month, day),
        flight_end=date(2026, month, 28),
        group_id=GROUP,
        agency_id=AGENCY,
        channel=channel,
        scope="national",
        revenue=Decimal(revenue),
    )


def test_two_flights_of_a_counter_are_applied_in_order():
    flights = [month_flight(1, 3, "90000"), month_flight(2, 4, "30000")]

    first, second = calculate_rebates([group_schedule()], flights, AS_OF)

    assert (first.position_before, first.position_after, first.rebate) == (Decimal(0), Decimal(90_000), Decimal(13_500))
    assert (second.position_before, second.position_after, second.rebate) == (
        Decimal(90_000), Decimal(120_000), Decimal(5_500),
    )
    assert second.effective_rate.quantize(Decimal("0.0001")) == Decimal("0.1833")


def test_a_crossing_is_forward_only():
    flights = [month_flight(1, 3, "90000"), month_flight(2, 4, "30000"), month_flight(3, 5, "10000")]

    first, second, third = calculate_rebates([group_schedule()], flights, AS_OF)

    assert first.effective_rate == Decimal("0.15")
    assert third.effective_rate == Decimal("0.20")


def test_a_year_of_flights_charges_the_marginal_total():
    flights = [month_flight(number, number, "100000") for number in range(1, 7)]

    results = calculate_rebates([group_schedule(THREE_BRACKETS)], flights, AS_OF)

    assert sum((result.rebate for result in results), Decimal(0)) == Decimal(120_000)
    assert results[-1].position_after == Decimal(600_000)


def test_the_order_of_the_input_does_not_matter():
    flights = [
        month_flight(1, 2, "40000"),
        month_flight(2, 3, "70000"),
        month_flight(3, 3, "25000", day=15),
        month_flight(4, 5, "10000"),
    ]
    expected = calculate_rebates([group_schedule()], flights, AS_OF)

    for permutation in itertools.permutations(flights):
        assert calculate_rebates([group_schedule()], list(permutation), AS_OF) == expected


def test_the_results_come_back_in_application_order():
    flights = [month_flight(9, 5, "1"), month_flight(8, 3, "1"), month_flight(7, 4, "1")]

    results = calculate_rebates([group_schedule()], flights, AS_OF)

    assert [result.flight_id for result in results] == [8, 7, 9]


def test_a_tie_on_flight_start_is_broken_by_id():
    flights = [month_flight(5, 3, "60000"), month_flight(3, 3, "60000")]

    lower_id, higher_id = calculate_rebates([group_schedule()], flights, AS_OF)

    assert (lower_id.flight_id, lower_id.position_before) == (3, Decimal(0))
    assert (higher_id.flight_id, higher_id.position_before) == (5, Decimal(60_000))


def test_the_start_date_decides_before_the_id():
    flights = [month_flight(1, 6, "60000"), month_flight(2, 3, "60000")]

    earlier, later = calculate_rebates([group_schedule()], flights, AS_OF)

    assert (earlier.flight_id, earlier.position_before) == (2, Decimal(0))
    assert (later.flight_id, later.position_before) == (1, Decimal(60_000))


def test_each_result_carries_what_applied_rates_will_freeze():
    (result,) = calculate_rebates([group_schedule()], [month_flight(1, 3, "30000")], AS_OF)

    assert result.step is LadderStep.GROUP
    assert result.agency_exception is False
    assert result.source_year == 2026
    assert result.schedule_id == 1
    assert result.zero_reason is None
    assert [charge.amount for charge in result.charges] == [Decimal(30_000)]


def test_a_flight_with_no_schedule_accrues_nothing_and_says_why():
    (result,) = calculate_rebates([], [month_flight(1, 3, "30000")], AS_OF)

    assert result.step is LadderStep.EXPLICIT_ZERO
    assert result.rebate == Decimal(0)
    assert result.effective_rate == Decimal(0)
    assert result.schedule_id is None
    assert result.zero_reason is not None
