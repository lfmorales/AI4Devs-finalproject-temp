"""Counters: one per (group, agency or none, channel, year); only closed flights advance them."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.domain.services.flight_margin import calculate_flight_margin, round_amount
from app.domain.services.rebate_engine import calculate_rebates
from app.domain.value_objects.margin import FlightEconomics
from app.domain.value_objects.rebate import Bracket, CounterKey, LadderStep, RebateFlight, RebateSchedule
from tests.domain.test_rebate_engine import AS_OF, GROUP, TWO_BRACKETS, group_schedule, month_flight
from tests.domain.test_rebate_ladder import AGENCY

FLAT_30 = (Bracket(Decimal(0), None, Decimal("0.30")),)


def agency_schedule(agency_id: int = AGENCY, channel: str | None = None, schedule_id: int = 2) -> RebateSchedule:
    return RebateSchedule(
        schedule_id=schedule_id, group_id=GROUP, agency_id=agency_id, channel=channel, scope=None,
        valid_from=date(2026, 1, 1), valid_to=None, brackets=FLAT_30,
    )


def by_id(results):
    return {result.flight_id: result for result in results}


def test_each_channel_runs_its_own_counter():
    flights = [
        month_flight(1, 3, "150000", channel="Directo"),
        month_flight(2, 4, "50000", channel="DOOH"),
        month_flight(3, 5, "10000", channel="Directo"),
    ]

    results = by_id(calculate_rebates([group_schedule()], flights, AS_OF))

    assert results[2].position_before == Decimal(0)
    assert results[2].effective_rate == Decimal("0.15")
    assert results[3].position_before == Decimal(150_000)
    assert results[3].effective_rate == Decimal("0.20")


def test_one_channels_volume_never_advances_anothers_bracket():
    flights = [month_flight(1, 3, "500000", channel="Directo"), month_flight(2, 4, "10000", channel="Deal")]

    results = by_id(calculate_rebates([group_schedule()], flights, AS_OF))

    assert results[2].counter == CounterKey(GROUP, None, "Deal", 2026)
    assert results[2].effective_rate == Decimal("0.15")


def test_one_group_can_sit_in_different_brackets_at_once():
    flights = [month_flight(1, 3, "150000", channel="Directo"), month_flight(2, 4, "30000", channel="CTV")]

    results = by_id(calculate_rebates([group_schedule()], flights, AS_OF))

    assert results[1].rebate == Decimal(100_000) * Decimal("0.15") + Decimal(50_000) * Decimal("0.20")
    assert results[2].effective_rate == Decimal("0.15")
    assert results[1].position_after == Decimal(150_000)
    assert results[2].position_after == Decimal(30_000)


def test_two_groups_never_share_a_counter():
    other_group = RebateSchedule(
        schedule_id=9, group_id=GROUP + 1, agency_id=None, channel=None, scope=None,
        valid_from=date(2026, 1, 1), valid_to=None, brackets=TWO_BRACKETS,
    )
    flights = [month_flight(1, 3, "90000"), replace(month_flight(2, 4, "30000"), group_id=GROUP + 1)]

    results = by_id(calculate_rebates([group_schedule(), other_group], flights, AS_OF))

    assert results[2].position_before == Decimal(0)
    assert results[2].counter.group_id == GROUP + 1


def test_an_agency_exception_accrues_on_the_agencys_own_counter():
    sibling = replace(month_flight(2, 4, "30000"), agency_id=AGENCY + 1)
    flights = [month_flight(1, 3, "90000"), sibling]

    results = by_id(calculate_rebates([group_schedule(), agency_schedule()], flights, AS_OF))

    assert results[1].counter == CounterKey(GROUP, AGENCY, "Directo", 2026)
    assert results[1].agency_exception is True
    assert results[1].rebate == Decimal(27_000)
    assert results[2].counter == CounterKey(GROUP, None, "Directo", 2026)
    assert results[2].position_before == Decimal(0)


def test_an_exception_without_a_channel_has_one_counter_per_channel():
    flights = [month_flight(1, 3, "90000", channel="Directo"), month_flight(2, 4, "50000", channel="Deal")]

    results = by_id(calculate_rebates([group_schedule(), agency_schedule()], flights, AS_OF))

    assert results[1].counter == CounterKey(GROUP, AGENCY, "Directo", 2026)
    assert results[2].counter == CounterKey(GROUP, AGENCY, "Deal", 2026)
    assert results[2].position_before == Decimal(0)
    assert results[1].step is results[2].step is LadderStep.AGENCY


def test_an_exception_for_one_channel_leaves_the_agencys_other_channel_on_the_group_counter():
    flights = [month_flight(1, 3, "90000", channel="Directo"), month_flight(2, 4, "50000", channel="Deal")]

    results = by_id(calculate_rebates([group_schedule(), agency_schedule(channel="Directo")], flights, AS_OF))

    assert results[1].counter.agency_id == AGENCY
    assert results[2].counter == CounterKey(GROUP, None, "Deal", 2026)
    assert results[2].agency_exception is False


def test_two_excepted_agencies_do_not_share_a_counter():
    flights = [month_flight(1, 3, "90000"), replace(month_flight(2, 4, "40000"), agency_id=AGENCY + 1)]
    schedules = [agency_schedule(AGENCY, schedule_id=2), agency_schedule(AGENCY + 1, schedule_id=3)]

    results = by_id(calculate_rebates(schedules, flights, AS_OF))

    assert results[2].counter == CounterKey(GROUP, AGENCY + 1, "Directo", 2026)
    assert results[2].position_before == Decimal(0)


JUNE_AS_OF = date(2026, 6, 10)


def june_flights() -> list[RebateFlight]:
    running = month_flight(3, 6, "30000")  # 1 to 28 June, still running on the 10th
    closed_later_start = replace(month_flight(4, 6, "5000", day=5), flight_end=date(2026, 6, 9))
    return [month_flight(1, 4, "50000"), month_flight(2, 5, "40000"), running, closed_later_start]


def test_a_running_flight_does_not_advance_the_counter():
    results = by_id(calculate_rebates([group_schedule()], june_flights(), JUNE_AS_OF))

    closed_after_it = results[4]
    assert closed_after_it.position_before == Decimal(90_000)  # 50,000 + 40,000, not the running 30,000
    assert results[3].position_after == results[3].position_before


def test_a_running_flight_starts_from_the_position_after_every_closed_flight():
    results = by_id(calculate_rebates([group_schedule()], june_flights(), JUNE_AS_OF))

    # Closed: 50,000 + 40,000 + 5,000 (the 5 to 9 June flight). The running flight reads 95,000.
    assert results[3].position_before == Decimal(95_000)
    assert results[3].rebate == Decimal("5000") * Decimal("0.15") + Decimal("25000") * Decimal("0.20")


def test_a_running_flights_rebate_is_computed_on_its_full_revenue():
    (result,) = calculate_rebates([group_schedule()], [month_flight(1, 6, "30000")], JUNE_AS_OF)

    assert [charge.amount for charge in result.charges] == [Decimal(30_000)]
    assert result.rebate == Decimal(4_500)


def test_the_margin_prorates_a_running_flights_full_rebate_by_elapsed_days():
    # 6,000,000 impressions at 5.00 EUR are 30,000 EUR of revenue over a 30-day window.
    september = RebateFlight(
        flight_id=2, flight_start=date(2026, 9, 1), flight_end=date(2026, 9, 30),
        group_id=GROUP, agency_id=AGENCY, channel="Directo", scope="national", revenue=Decimal(30_000),
    )
    closed_august = replace(month_flight(1, 8, "90000"), flight_end=date(2026, 8, 31))
    as_of = date(2026, 9, 10)

    results = by_id(calculate_rebates([group_schedule()], [closed_august, september], as_of))
    full_rebate = results[2].rebate
    margin = calculate_flight_margin(
        FlightEconomics(
            flight_start=date(2026, 9, 1), flight_end=date(2026, 9, 30),
            contracted_impressions=6_000_000, sale_cpm=Decimal("5.00"),
            delivered_impressions=0, media_cost=Decimal(0), rebate_amount=full_rebate, platform_rate=Decimal("1.00"),
        ),
        as_of,
    )

    assert full_rebate == Decimal(5_500)
    assert margin.revenue == Decimal("10000.00")  # 30,000 x 10 / 30
    assert margin.rebate == round_amount(full_rebate * 10 / 30) == Decimal("1833.33")


def test_a_flight_that_has_not_started_is_not_in_the_results():
    future = month_flight(2, 9, "1000")

    results = calculate_rebates([group_schedule()], [month_flight(1, 3, "1000"), future], date(2026, 6, 1))

    assert [result.flight_id for result in results] == [1]


def test_a_flight_starting_on_the_first_of_january_belongs_to_the_new_year():
    december = RebateFlight(1, date(2026, 12, 1), date(2026, 12, 31), GROUP, AGENCY, "Directo", "national", Decimal(500_000))
    january = RebateFlight(2, date(2027, 1, 1), date(2027, 1, 31), GROUP, AGENCY, "Directo", "national", Decimal(10_000))
    open_ended = RebateSchedule(1, GROUP, None, None, None, date(2026, 1, 1), None, TWO_BRACKETS)

    results = by_id(calculate_rebates([open_ended], [december, january], date(2027, 2, 1)))

    assert results[1].counter.year == 2026
    assert results[2].counter.year == 2027
    assert results[2].position_before == Decimal(0)
    assert results[2].effective_rate == Decimal("0.15")


def test_a_flight_on_the_last_day_of_the_year_belongs_to_the_old_year():
    last_day = RebateFlight(1, date(2026, 12, 31), date(2026, 12, 31), GROUP, AGENCY, "Directo", "national", Decimal(10))

    (result,) = calculate_rebates([group_schedule()], [last_day], date(2027, 1, 5))

    assert result.counter.year == 2026
