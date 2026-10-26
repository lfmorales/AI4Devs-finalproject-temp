"""Opening positions let a closing start a counter from what is already frozen, without pricing frozen flights again."""

from datetime import date
from decimal import Decimal

from app.domain.services.rebate_engine import calculate_rebates
from app.domain.value_objects.rebate import CounterKey
from tests.domain.test_rebate_engine import GROUP, group_schedule, month_flight
from tests.domain.test_rebate_order_independence import AS_OF, _exception_flights, _schedules

DIRECTO_2026 = CounterKey(GROUP, None, "Directo", 2026)


def test_an_empty_opening_gives_exactly_the_previous_results():
    without = calculate_rebates(_schedules(), _exception_flights(), AS_OF)

    assert calculate_rebates(_schedules(), _exception_flights(), AS_OF, opening_positions={}) == without
    assert calculate_rebates(_schedules(), _exception_flights(), AS_OF, opening_positions=None) == without


def test_an_opening_position_shifts_the_counter():
    flights = [month_flight(1, 4, "30000")]

    (result,) = calculate_rebates([group_schedule()], flights, date(2026, 12, 31), {DIRECTO_2026: Decimal(90_000)})

    assert result.position_before == Decimal(90_000)
    assert result.position_after == Decimal(120_000)
    assert result.rebate == Decimal(5_500)  # 10,000 at 15 % and 20,000 at 20 %


def test_an_opening_position_for_another_counter_changes_nothing():
    flights = [month_flight(1, 4, "30000")]
    other = {CounterKey(GROUP, None, "Deal", 2026): Decimal(500_000), CounterKey(GROUP, None, "Directo", 2025): Decimal(1)}

    assert calculate_rebates([group_schedule()], flights, date(2026, 12, 31), other) == calculate_rebates(
        [group_schedule()], flights, date(2026, 12, 31)
    )


def test_later_flights_add_to_the_opening():
    flights = [month_flight(1, 4, "30000"), month_flight(2, 5, "10000")]

    first, second = calculate_rebates([group_schedule()], flights, date(2026, 12, 31), {DIRECTO_2026: Decimal(90_000)})

    assert second.position_before == Decimal(120_000)
    assert second.effective_rate == Decimal("0.20")


def test_a_running_flight_reads_the_opening_plus_the_closed_flights():
    closed = month_flight(1, 4, "30000")
    running = month_flight(2, 6, "10000")

    results = {
        r.flight_id: r
        for r in calculate_rebates([group_schedule()], [closed, running], date(2026, 6, 10), {DIRECTO_2026: Decimal(50_000)})
    }

    assert results[2].position_before == Decimal(80_000)
    assert results[2].position_after == Decimal(80_000)
