"""The development seed: the user gets finance on top of operations, nothing is removed, and it is idempotent."""

from decimal import Decimal

from sqlalchemy import func, select

from app.infrastructure.persistence.models.identity import RoleRecord, UserRecord, UserRoleRecord
from app.infrastructure.persistence.models.margin import (
    PlatformRateSettingRecord,
    RebateBracketRecord,
    RebateScheduleRecord,
)
from app.infrastructure.persistence.models.masters import AgencyRecord, HoldingGroupRecord
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


def test_it_leaves_one_fictitious_schedule_and_one_fictitious_rate(rolled_back_session):
    seed(rolled_back_session, EMAIL)

    group = rolled_back_session.scalar(select(HoldingGroupRecord).where(HoldingGroupRecord.name == "Default Holding Group"))
    schedule = rolled_back_session.scalar(select(RebateScheduleRecord).where(RebateScheduleRecord.holding_group_id == group.id))
    brackets = rolled_back_session.scalars(
        select(RebateBracketRecord).where(RebateBracketRecord.rebate_schedule_id == schedule.id).order_by(RebateBracketRecord.position)
    ).all()
    agency = rolled_back_session.scalar(select(AgencyRecord).where(AgencyRecord.name == "Test Agency"))
    rates = rolled_back_session.scalars(select(PlatformRateSettingRecord).where(PlatformRateSettingRecord.level == "agency")).all()
    author = rolled_back_session.scalar(select(UserRecord).where(UserRecord.email == EMAIL))

    assert (schedule.agency_id, schedule.channel_id, schedule.scope, schedule.valid_to) == (None, None, None, None)
    assert [(b.lower, b.upper, b.rate) for b in brackets] == [
        (Decimal(0), Decimal(100000), Decimal("0.10")), (Decimal(100000), None, Decimal("0.15"))]
    assert [(r.agency_id, r.rate_per_thousand, r.created_by) for r in rates] == [(agency.id, Decimal("1.10"), author.id)]


def test_the_system_rate_of_the_migration_is_left_alone(rolled_back_session):
    seed(rolled_back_session, EMAIL)

    system = rolled_back_session.scalars(select(PlatformRateSettingRecord).where(PlatformRateSettingRecord.level == "system")).all()

    assert [row.rate_per_thousand for row in system] == [Decimal("1.00")]
