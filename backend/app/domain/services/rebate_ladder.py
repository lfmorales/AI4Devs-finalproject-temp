from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.exceptions import RebateRuleError
from app.domain.value_objects.rebate import LadderStep, RebateFlight, RebateSchedule, ResolvedRebate, ZeroReason


@dataclass(frozen=True)
class _MatchKey:
    """One row of the ladder: which parts of the flight the schedule must name."""

    step: LadderStep
    agency: bool
    channel: bool
    scope: bool


# Progressively wider keys, walked in order. Adding a step is adding a row.
_LADDER: tuple[_MatchKey, ...] = (
    _MatchKey(LadderStep.AGENCY_CHANNEL_SCOPE, agency=True, channel=True, scope=True),
    _MatchKey(LadderStep.AGENCY_CHANNEL, agency=True, channel=True, scope=False),
    _MatchKey(LadderStep.AGENCY, agency=True, channel=False, scope=False),
    _MatchKey(LadderStep.GROUP_CHANNEL_SCOPE, agency=False, channel=True, scope=True),
    _MatchKey(LadderStep.GROUP_CHANNEL, agency=False, channel=True, scope=False),
    _MatchKey(LadderStep.GROUP, agency=False, channel=False, scope=False),
)


def _matches(schedule: RebateSchedule, key: _MatchKey, flight: RebateFlight) -> bool:
    """A part the key names must equal the flight's; a part it does not name must be absent from the schedule."""
    if key.agency:
        agency_matches = schedule.agency_id == flight.agency_id
    else:
        agency_matches = schedule.agency_id is None and schedule.group_id == flight.group_id
    channel_matches = schedule.channel == (flight.channel if key.channel else None)
    scope_matches = schedule.scope == (flight.scope if key.scope else None)
    return agency_matches and channel_matches and scope_matches


def resolve_rebate_schedule(schedules: Sequence[RebateSchedule], flight: RebateFlight) -> ResolvedRebate:
    """Walk the ladder in the table in force on `flight_start` and stop at the first step that matches.

    Two schedules matching at one step are ambiguous and raise `overlapping_schedules`. With no match the
    result is an explicit zero at step 8.
    """
    in_force = [schedule for schedule in schedules if schedule.in_force_on(flight.flight_start)]
    for key in _LADDER:
        matching = [schedule for schedule in in_force if _matches(schedule, key, flight)]
        if len(matching) > 1:
            ids = sorted(schedule.schedule_id for schedule in matching)
            raise RebateRuleError("overlapping_schedules", f"schedules {ids} all match at ladder step {int(key.step)}")
        if matching:
            return ResolvedRebate(
                schedule=matching[0],
                step=key.step,
                agency_exception=key.agency,
                source_year=matching[0].valid_from.year,
                zero_reason=None,
            )
    return ResolvedRebate(
        schedule=None, step=LadderStep.EXPLICIT_ZERO, agency_exception=False, source_year=None,
        zero_reason=ZeroReason.NO_SCHEDULE,
    )
