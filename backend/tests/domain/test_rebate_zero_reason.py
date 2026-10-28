"""A zero from a hole in the data is not a zero that was negotiated, and says why it is a zero."""

from datetime import date
from decimal import Decimal

from app.domain.services.rebate_ladder import resolve_rebate_schedule
from app.domain.value_objects.rebate import LadderStep, ZeroReason
from tests.domain.test_rebate_ladder import GROUP, flat_schedule, flight


def test_no_schedule_of_any_group_in_force_is_no_schedule_for_year():
    resolved = resolve_rebate_schedule([], flight())

    assert resolved.step is LadderStep.EXPLICIT_ZERO
    assert resolved.zero_reason is ZeroReason.NO_SCHEDULE_FOR_YEAR


def test_schedules_only_for_other_years_is_no_schedule_for_year():
    last_year = flat_schedule(1, "0.10", valid_from=date(2025, 1, 1), valid_to=date(2025, 12, 31))

    assert resolve_rebate_schedule([last_year], flight()).zero_reason is ZeroReason.NO_SCHEDULE_FOR_YEAR


def test_schedules_in_force_but_none_for_the_group_is_no_schedule():
    other_group = flat_schedule(1, "0.10", group_id=GROUP + 1)

    resolved = resolve_rebate_schedule([other_group], flight())

    assert resolved.step is LadderStep.EXPLICIT_ZERO
    assert resolved.zero_reason is ZeroReason.NO_SCHEDULE


def test_the_group_has_schedules_but_none_matches_the_flight_is_no_schedule():
    other_channel = flat_schedule(1, "0.10", channel="Deal")

    assert resolve_rebate_schedule([other_channel], flight(channel="Directo")).zero_reason is ZeroReason.NO_SCHEDULE


def test_a_negotiated_zero_resolves_at_a_real_step_and_has_no_zero_reason():
    negotiated = flat_schedule(1, "0", channel="Directo", scope="national")

    resolved = resolve_rebate_schedule([negotiated], flight())

    assert resolved.step is LadderStep.GROUP_CHANNEL_SCOPE
    assert resolved.zero_reason is None
    assert resolved.schedule is negotiated
    assert resolved.schedule.brackets[0].rate == Decimal(0)


def test_the_two_zeros_can_be_told_apart():
    negotiated = resolve_rebate_schedule([flat_schedule(1, "0")], flight())
    defaulted = resolve_rebate_schedule([], flight())

    assert (negotiated.step, negotiated.zero_reason) != (defaulted.step, defaulted.zero_reason)
    assert negotiated.schedule is not None
    assert defaulted.schedule is None


def test_a_resolved_schedule_never_carries_a_zero_reason():
    resolved = resolve_rebate_schedule([flat_schedule(1, "0.10")], flight())

    assert resolved.zero_reason is None
