"""The development seed: the user gets finance on top of operations, nothing is removed, and it is idempotent.

It also carries the four channels of the catalogue and a fictitious rebate schedule for CTV only.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import ScalarResult, delete, func, select
from sqlalchemy.orm import Session

from app.domain.services.rebate_ladder import resolve_rebate_schedule
from app.domain.value_objects.rebate import LadderStep, RebateFlight
from app.infrastructure.persistence.models.identity import RoleRecord, UserRecord, UserRoleRecord
from app.infrastructure.persistence.models.margin import (
    PlatformRateSettingRecord,
    RebateBracketRecord,
    RebateScheduleRecord,
)
from app.infrastructure.persistence.models.masters import AgencyRecord, ChannelRecord, HoldingGroupRecord
from app.infrastructure.persistence.repositories.sqlalchemy_margin_repositories import (
    SqlAlchemyRebateScheduleRepository,
)
from scripts.seed_dev_data import seed

EMAIL = "dev.finance@example.org"


def _roles_of(session, email: str) -> set[str]:
    return set(session.scalars(
        select(RoleRecord.name)
        .join(UserRoleRecord, UserRoleRecord.role_id == RoleRecord.id)
        .join(UserRecord, UserRecord.id == UserRoleRecord.user_id)
        .where(UserRecord.email == email)
    ))


def _counts(session) -> dict[str, int]:
    return {
        model.__tablename__: session.scalar(select(func.count()).select_from(model))
        for model in (RoleRecord, UserRecord, UserRoleRecord, RebateScheduleRecord, RebateBracketRecord, PlatformRateSettingRecord)
    }


def test_the_development_user_holds_operations_and_finance(rolled_back_session):
    seed(rolled_back_session, EMAIL)

    assert _roles_of(rolled_back_session, EMAIL) == {"operations", "finance"}


def test_a_role_the_user_already_held_is_not_removed(rolled_back_session):
    seed(rolled_back_session, EMAIL)
    user = rolled_back_session.scalar(select(UserRecord).where(UserRecord.email == EMAIL))
    business = rolled_back_session.scalar(select(RoleRecord).where(RoleRecord.name == "business"))
    rolled_back_session.add(UserRoleRecord(user_id=user.id, role_id=business.id))
    rolled_back_session.flush()

    seed(rolled_back_session, EMAIL)

    assert _roles_of(rolled_back_session, EMAIL) == {"operations", "finance", "business"}


def test_running_the_seed_twice_changes_nothing_the_second_time(rolled_back_session):
    seed(rolled_back_session, EMAIL)
    first = _counts(rolled_back_session)

    seed(rolled_back_session, EMAIL)

    assert _counts(rolled_back_session) == first


def _any_channel_schedules(session: Session, group_id: int) -> ScalarResult[RebateScheduleRecord]:
    """The group's schedule for any agency, channel and scope: the key the exclusion constraint compares, with
    one validity period in the seed."""
    return session.scalars(select(RebateScheduleRecord).where(
        RebateScheduleRecord.holding_group_id == group_id,
        RebateScheduleRecord.agency_id.is_(None),
        RebateScheduleRecord.channel_id.is_(None),
        RebateScheduleRecord.scope.is_(None),
    ))


def test_it_leaves_one_fictitious_any_channel_schedule_and_one_fictitious_rate(rolled_back_session: Session) -> None:
    seed(rolled_back_session, EMAIL)

    group = rolled_back_session.scalars(
        select(HoldingGroupRecord).where(HoldingGroupRecord.name == "Default Holding Group")
    ).one()
    schedule = _any_channel_schedules(rolled_back_session, group.id).one()
    brackets = rolled_back_session.scalars(
        select(RebateBracketRecord).where(RebateBracketRecord.rebate_schedule_id == schedule.id).order_by(RebateBracketRecord.position)
    ).all()
    agency = rolled_back_session.scalars(select(AgencyRecord).where(AgencyRecord.name == "Test Agency")).one()
    rates = rolled_back_session.scalars(select(PlatformRateSettingRecord).where(PlatformRateSettingRecord.level == "agency")).all()
    author = rolled_back_session.scalars(select(UserRecord).where(UserRecord.email == EMAIL)).one()

    assert (schedule.agency_id, schedule.channel_id, schedule.scope, schedule.valid_to) == (None, None, None, None)
    assert [(b.lower, b.upper, b.rate) for b in brackets] == [
        (Decimal(0), Decimal(100000), Decimal("0.10")), (Decimal(100000), None, Decimal("0.15"))]
    assert [(r.agency_id, r.rate_per_thousand, r.created_by) for r in rates] == [(agency.id, Decimal("1.10"), author.id)]


def test_the_any_channel_schedule_is_created_even_when_the_group_has_other_schedules_without_a_channel(
    rolled_back_session: Session,
) -> None:
    seed(rolled_back_session, EMAIL)
    group = rolled_back_session.scalars(
        select(HoldingGroupRecord).where(HoldingGroupRecord.name == "Default Holding Group")
    ).one()
    agency = rolled_back_session.scalars(select(AgencyRecord).where(AgencyRecord.name == "Test Agency")).one()
    seeded = _any_channel_schedules(rolled_back_session, group.id).one()
    rolled_back_session.execute(delete(RebateBracketRecord).where(RebateBracketRecord.rebate_schedule_id == seeded.id))
    rolled_back_session.execute(delete(RebateScheduleRecord).where(RebateScheduleRecord.id == seeded.id))
    # Both have no channel, but neither is the group's schedule for any agency and any scope.
    rolled_back_session.add_all([
        RebateScheduleRecord(holding_group_id=group.id, agency_id=agency.id, channel_id=None, scope=None,
                             valid_from=date(2026, 1, 1)),
        RebateScheduleRecord(holding_group_id=group.id, agency_id=None, channel_id=None, scope="national",
                             valid_from=date(2026, 1, 1)),
    ])
    rolled_back_session.flush()

    seed(rolled_back_session, EMAIL)

    recreated = _any_channel_schedules(rolled_back_session, group.id).one()
    brackets = rolled_back_session.scalars(
        select(RebateBracketRecord).where(RebateBracketRecord.rebate_schedule_id == recreated.id)
        .order_by(RebateBracketRecord.position)
    ).all()
    assert [(b.lower, b.upper, b.rate) for b in brackets] == [
        (Decimal(0), Decimal(100000), Decimal("0.10")), (Decimal(100000), None, Decimal("0.15"))]
    others = rolled_back_session.scalars(select(RebateBracketRecord).where(
        RebateBracketRecord.rebate_schedule_id.in_(
            select(RebateScheduleRecord.id).where(RebateScheduleRecord.id != recreated.id,
                                                  RebateScheduleRecord.channel_id.is_(None),
                                                  RebateScheduleRecord.holding_group_id == group.id))
    )).all()
    assert others == []


def test_the_seed_loads_exactly_the_four_channels(rolled_back_session: Session) -> None:
    seed(rolled_back_session, EMAIL)

    names = set(rolled_back_session.scalars(select(ChannelRecord.name)))

    assert names == {"Directo", "Deal", "DOOH", "CTV"}
    assert not names & {"OOH", "Digital"}


def test_it_adds_a_fictitious_schedule_for_ctv_only(rolled_back_session: Session) -> None:
    seed(rolled_back_session, EMAIL)

    group = rolled_back_session.scalars(
        select(HoldingGroupRecord).where(HoldingGroupRecord.name == "Default Holding Group")
    ).one()
    ctv = rolled_back_session.scalars(select(ChannelRecord).where(ChannelRecord.name == "CTV")).one()
    schedules = rolled_back_session.scalars(
        select(RebateScheduleRecord).where(RebateScheduleRecord.holding_group_id == group.id)
    ).all()
    ctv_schedules = [schedule for schedule in schedules if schedule.channel_id is not None]
    brackets = rolled_back_session.scalars(
        select(RebateBracketRecord).where(RebateBracketRecord.rebate_schedule_id == ctv_schedules[0].id)
        .order_by(RebateBracketRecord.position)
    ).all()

    assert sorted(schedule.channel_id is None for schedule in schedules) == [False, True]
    assert [(s.channel_id, s.agency_id, s.scope, s.valid_to) for s in ctv_schedules] == [(ctv.id, None, None, None)]
    assert [(b.lower, b.upper, b.rate) for b in brackets] == [
        (Decimal(0), Decimal(50000), Decimal("0.05")), (Decimal(50000), None, Decimal("0.08"))]


def _flight_of(session: Session, channel: str) -> RebateFlight:
    group = session.scalars(select(HoldingGroupRecord).where(HoldingGroupRecord.name == "Default Holding Group")).one()
    agency = session.scalars(select(AgencyRecord).where(AgencyRecord.name == "Test Agency")).one()
    return RebateFlight(
        flight_id=1, flight_start=date(2026, 3, 1), flight_end=date(2026, 3, 31), group_id=group.id,
        agency_id=agency.id, channel=channel, scope="national", revenue=Decimal("1000.00"),
    )


def test_a_ctv_line_of_the_seeded_group_resolves_the_ctv_schedule(rolled_back_session: Session) -> None:
    seed(rolled_back_session, EMAIL)
    schedules = SqlAlchemyRebateScheduleRepository(rolled_back_session).list_schedules()

    resolved = resolve_rebate_schedule(schedules, _flight_of(rolled_back_session, "CTV"))

    assert resolved.step is LadderStep.GROUP_CHANNEL
    assert resolved.schedule is not None and resolved.schedule.channel == "CTV"


def test_a_directo_line_of_the_seeded_group_resolves_the_any_channel_schedule(rolled_back_session: Session) -> None:
    seed(rolled_back_session, EMAIL)
    schedules = SqlAlchemyRebateScheduleRepository(rolled_back_session).list_schedules()

    resolved = resolve_rebate_schedule(schedules, _flight_of(rolled_back_session, "Directo"))

    assert resolved.step is LadderStep.GROUP
    assert resolved.schedule is not None and resolved.schedule.channel is None


def test_the_system_rate_of_the_migration_is_left_alone(rolled_back_session):
    seed(rolled_back_session, EMAIL)

    system = rolled_back_session.scalars(select(PlatformRateSettingRecord).where(PlatformRateSettingRecord.level == "system")).all()

    assert [row.rate_per_thousand for row in system] == [Decimal("1.00")]


def test_the_seed_creates_the_trading_role_row_once(rolled_back_session):
    rolled_back_session.query(UserRoleRecord).filter(
        UserRoleRecord.role_id.in_(select(RoleRecord.id).where(RoleRecord.name == "trading"))
    ).delete(synchronize_session=False)
    rolled_back_session.query(RoleRecord).filter(RoleRecord.name == "trading").delete(synchronize_session=False)

    seed(rolled_back_session, EMAIL)
    seed(rolled_back_session, EMAIL)

    assert rolled_back_session.scalar(
        select(func.count()).select_from(RoleRecord).where(RoleRecord.name == "trading")
    ) == 1


def test_the_seed_gives_dooh_the_ots_metric_and_the_other_channels_impressions(rolled_back_session: Session) -> None:
    seed(rolled_back_session, EMAIL)

    metrics = dict(rolled_back_session.execute(select(ChannelRecord.name, ChannelRecord.delivery_metric)).all())

    assert metrics == {"Directo": "impressions", "Deal": "impressions", "DOOH": "ots", "CTV": "impressions"}
