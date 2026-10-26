"""An agency exception wins over its group; scope narrows before it widens; a channel-less schedule serves every channel."""

from decimal import Decimal

from app.domain.services.rebate_ladder import resolve_rebate_schedule
from app.domain.value_objects.rebate import LadderStep
from tests.domain.test_rebate_ladder import AGENCY, GROUP, flat_schedule, flight


def test_an_agency_exception_wins_over_its_groups_schedule():
    group = flat_schedule(1, "0.25", channel="Directo", scope="national")
    exception = flat_schedule(2, "0.10", agency_id=AGENCY, channel="Directo")

    resolved = resolve_rebate_schedule([group, exception], flight())

    assert resolved.schedule is exception
    assert resolved.agency_exception is True


def test_a_wider_agency_exception_still_wins_over_a_more_specific_group_schedule():
    group = flat_schedule(1, "0.25", channel="Directo", scope="national")
    exception = flat_schedule(2, "0.10", agency_id=AGENCY)

    resolved = resolve_rebate_schedule([group, exception], flight())

    assert resolved.schedule is exception
    assert resolved.step is LadderStep.AGENCY


def test_an_exception_of_another_agency_does_not_apply():
    other_agency = flat_schedule(1, "0.10", agency_id=AGENCY + 1, channel="Directo", scope="national")
    group = flat_schedule(2, "0.25")

    resolved = resolve_rebate_schedule([other_agency, group], flight())

    assert resolved.schedule is group
    assert resolved.agency_exception is False


def test_a_schedule_of_another_group_does_not_apply():
    other_group = flat_schedule(1, "0.10", group_id=GROUP + 1, channel="Directo", scope="national")

    assert resolve_rebate_schedule([other_group], flight()).step is LadderStep.EXPLICIT_ZERO


def test_the_scoped_schedule_is_preferred_to_the_scopeless_one():
    scopeless = flat_schedule(1, "0.20", channel="Directo")
    scoped = flat_schedule(2, "0.15", channel="Directo", scope="national")

    resolved = resolve_rebate_schedule([scopeless, scoped], flight(scope="national"))

    assert resolved.schedule is scoped
    assert resolved.step is LadderStep.GROUP_CHANNEL_SCOPE


def test_the_scopeless_schedule_serves_a_scope_that_has_no_schedule_of_its_own():
    scopeless = flat_schedule(1, "0.20", channel="Directo")
    national = flat_schedule(2, "0.15", channel="Directo", scope="national")

    resolved = resolve_rebate_schedule([scopeless, national], flight(scope="international"))

    assert resolved.schedule is scopeless
    assert resolved.step is LadderStep.GROUP_CHANNEL


def test_two_scopes_priced_differently_resolve_to_their_own_rate():
    national = flat_schedule(1, "0.20", channel="Directo", scope="national")
    international = flat_schedule(2, "0.15", channel="Directo", scope="international")

    assert resolve_rebate_schedule([national, international], flight(scope="national")).schedule is national
    assert resolve_rebate_schedule([national, international], flight(scope="international")).schedule is international


def test_a_scoped_schedule_never_serves_the_other_scope():
    national = flat_schedule(1, "0.20", channel="Directo", scope="national")

    assert resolve_rebate_schedule([national], flight(scope="international")).step is LadderStep.EXPLICIT_ZERO


def test_the_same_narrowing_applies_to_an_agency_exception():
    scopeless = flat_schedule(1, "0.20", agency_id=AGENCY, channel="Directo")
    scoped = flat_schedule(2, "0.15", agency_id=AGENCY, channel="Directo", scope="national")

    assert resolve_rebate_schedule([scopeless, scoped], flight()).schedule is scoped


def test_a_channel_less_schedule_serves_every_channel():
    group_only = flat_schedule(1, "0.12")

    for channel in ("Directo", "Deal", "DOOH", "CTV"):
        resolved = resolve_rebate_schedule([group_only], flight(channel=channel))
        assert resolved.schedule is group_only
        assert resolved.step is LadderStep.GROUP


def test_a_schedule_for_one_channel_does_not_serve_another():
    directo = flat_schedule(1, "0.12", channel="Directo")

    assert resolve_rebate_schedule([directo], flight(channel="Deal")).step is LadderStep.EXPLICIT_ZERO


def test_a_channel_less_agency_exception_covers_every_channel():
    exception = flat_schedule(1, "0.30", agency_id=AGENCY)
    group = flat_schedule(2, "0.10", channel="Directo")

    for channel in ("Directo", "Deal"):
        resolved = resolve_rebate_schedule([exception, group], flight(channel=channel))
        assert resolved.schedule is exception
        assert resolved.schedule.brackets[0].rate == Decimal("0.30")
