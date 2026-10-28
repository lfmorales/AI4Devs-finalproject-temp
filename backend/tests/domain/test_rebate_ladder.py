"""The rebate schedule is found by walking a ladder from the most specific key to the most general.

Steps (docs/product-description.md §5.9), evaluated in the table in force on `flight_start`:
1 agency, channel, scope; 2 agency, channel; 3 agency; 4 group, channel, scope; 5 group, channel; 6 group.
Step 7 (the previous table) is deferred; step 8 is an explicit zero.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.exceptions import RebateRuleError
from app.domain.services.rebate_ladder import resolve_rebate_schedule
from app.domain.value_objects.rebate import Bracket, LadderStep, RebateFlight, RebateSchedule

GROUP = 10
AGENCY = 20
FLIGHT_START = date(2026, 5, 4)


def flat_schedule(
    schedule_id: int,
    rate: str,
    *,
    group_id: int = GROUP,
    agency_id: int | None = None,
    channel: str | None = None,
    scope: str | None = None,
    valid_from: date = date(2026, 1, 1),
    valid_to: date | None = date(2026, 12, 31),
) -> RebateSchedule:
    return RebateSchedule(
        schedule_id=schedule_id,
        group_id=group_id,
        agency_id=agency_id,
        channel=channel,
        scope=scope,
        valid_from=valid_from,
        valid_to=valid_to,
        brackets=(Bracket(lower=Decimal(0), upper=None, rate=Decimal(rate)),),
    )


def flight(
    *,
    flight_id: int = 1,
    flight_start: date = FLIGHT_START,
    group_id: int = GROUP,
    agency_id: int = AGENCY,
    channel: str = "Directo",
    scope: str = "national",
    revenue: str = "1000.00",
) -> RebateFlight:
    return RebateFlight(
        flight_id=flight_id,
        flight_start=flight_start,
        flight_end=date(2026, 5, 31),
        group_id=group_id,
        agency_id=agency_id,
        channel=channel,
        scope=scope,
        revenue=Decimal(revenue),
    )


# One schedule per step, each at a rate that names its step: step 1 is 1 %, step 2 is 2 %, and so on.
LADDER = {
    1: flat_schedule(101, "0.01", agency_id=AGENCY, channel="Directo", scope="national"),
    2: flat_schedule(102, "0.02", agency_id=AGENCY, channel="Directo"),
    3: flat_schedule(103, "0.03", agency_id=AGENCY),
    4: flat_schedule(104, "0.04", channel="Directo", scope="national"),
    5: flat_schedule(105, "0.05", channel="Directo"),
    6: flat_schedule(106, "0.06"),
}


@pytest.mark.parametrize("step", [1, 2, 3, 4, 5, 6])
def test_each_step_resolves_when_no_more_specific_schedule_exists(step: int):
    # Every schedule from this step downwards exists; everything more specific is absent.
    schedules = [LADDER[number] for number in range(step, 7)]

    resolved = resolve_rebate_schedule(schedules, flight())

    assert resolved.step is LadderStep(step)
    assert resolved.schedule is LADDER[step]
    assert resolved.schedule.brackets[0].rate == Decimal(step) / Decimal(100)


@pytest.mark.parametrize("step", [1, 2, 3])
def test_an_agency_step_is_an_agency_exception(step: int):
    resolved = resolve_rebate_schedule([LADDER[step]], flight())

    assert resolved.agency_exception is True


@pytest.mark.parametrize("step", [4, 5, 6])
def test_a_group_step_is_not_an_agency_exception(step: int):
    resolved = resolve_rebate_schedule([LADDER[step]], flight())

    assert resolved.agency_exception is False


def test_the_walk_stops_at_the_first_match():
    resolved = resolve_rebate_schedule(list(LADDER.values()), flight())

    assert resolved.step is LadderStep.AGENCY_CHANNEL_SCOPE


def test_the_ladder_is_the_same_whatever_the_order_of_the_schedules():
    schedules = list(reversed(list(LADDER.values())))

    assert resolve_rebate_schedule(schedules, flight()).step is LadderStep.AGENCY_CHANNEL_SCOPE


def test_the_source_year_is_the_year_the_matched_schedule_starts():
    carried = flat_schedule(201, "0.10", valid_from=date(2024, 1, 1), valid_to=date(2026, 12, 31))

    resolved = resolve_rebate_schedule([carried], flight())

    assert resolved.source_year == 2024


def test_the_table_in_force_on_flight_start_is_the_one_used():
    may = flat_schedule(301, "0.10", valid_from=date(2026, 5, 1), valid_to=date(2026, 5, 31))
    june = flat_schedule(302, "0.20", valid_from=date(2026, 6, 1), valid_to=date(2026, 6, 30))
    spanning_flight = flight(flight_start=date(2026, 5, 20))  # ends 31 May

    assert resolve_rebate_schedule([may, june], spanning_flight).schedule is may


def test_the_validity_includes_both_of_its_ends():
    schedule = flat_schedule(401, "0.10", valid_from=date(2026, 5, 4), valid_to=date(2026, 5, 4))

    assert resolve_rebate_schedule([schedule], flight(flight_start=date(2026, 5, 4))).schedule is schedule
    assert resolve_rebate_schedule([schedule], flight(flight_start=date(2026, 5, 5))).step is LadderStep.EXPLICIT_ZERO
    assert resolve_rebate_schedule([schedule], flight(flight_start=date(2026, 5, 3))).step is LadderStep.EXPLICIT_ZERO


def test_an_open_ended_schedule_stays_in_force():
    schedule = flat_schedule(402, "0.10", valid_from=date(2026, 1, 1), valid_to=None)

    assert resolve_rebate_schedule([schedule], flight(flight_start=date(2030, 3, 1))).schedule is schedule


def test_a_schedule_ending_before_the_flight_starts_is_not_used():
    ended = flat_schedule(403, "0.10", valid_to=date(2026, 5, 3))

    assert resolve_rebate_schedule([ended], flight()).step is LadderStep.EXPLICIT_ZERO


def test_with_no_schedule_the_result_is_an_explicit_zero_at_step_8():
    resolved = resolve_rebate_schedule([], flight())

    assert resolved.step is LadderStep.EXPLICIT_ZERO
    assert resolved.step == 8
    assert resolved.schedule is None
    assert resolved.agency_exception is False
    assert resolved.source_year is None


def test_two_schedules_matching_at_the_same_step_are_a_domain_error():
    first = flat_schedule(501, "0.10")
    second = flat_schedule(502, "0.20", valid_from=date(2026, 3, 1))

    with pytest.raises(RebateRuleError) as raised:
        resolve_rebate_schedule([first, second], flight())

    assert raised.value.code == "overlapping_schedules"
