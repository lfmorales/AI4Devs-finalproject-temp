"""Builders for the margin tests: schedules, volumes and deliveries on top of the delivery fixtures."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignRecord,
)
from app.infrastructure.persistence.models.margin import RebateBracketRecord, RebateScheduleRecord
from app.infrastructure.persistence.models.masters import AgencyRecord


def group_of(session: Session, campaign_line_id: int) -> int:
    line = session.get(CampaignLineRecord, campaign_line_id)
    campaign = session.get(CampaignRecord, line.campaign_id)
    return session.get(AgencyRecord, campaign.agency_id).holding_group_id


def agency_of(session: Session, campaign_line_id: int) -> int:
    line = session.get(CampaignLineRecord, campaign_line_id)
    return session.get(CampaignRecord, line.campaign_id).agency_id


def add_schedule(
    session: Session,
    group_id: int,
    *brackets: tuple[str, str | None, str],
    valid_from: date = date(2026, 1, 1),
    valid_to: date | None = None,
) -> int:
    """A group-wide schedule. Each bracket is (lower, upper or None, rate)."""
    schedule = RebateScheduleRecord(holding_group_id=group_id, valid_from=valid_from, valid_to=valid_to)
    session.add(schedule)
    session.flush()
    for position, (lower, upper, rate) in enumerate(brackets, start=1):
        session.add(RebateBracketRecord(
            rebate_schedule_id=schedule.id, position=position, lower=Decimal(lower),
            upper=None if upper is None else Decimal(upper), rate=Decimal(rate)))
    session.flush()
    return schedule.id


def set_rate(session: Session, schedule_id: int, rate: str) -> None:
    session.execute(
        update(RebateBracketRecord).where(RebateBracketRecord.rebate_schedule_id == schedule_id).values(rate=Decimal(rate))
    )
    session.flush()


def set_volume(session: Session, campaign_line_id: int, impressions: int, cpm: str = "5.00") -> None:
    """Give the line, and every flight it has, this volume at this CPM."""
    session.execute(update(CampaignLineRecord).where(CampaignLineRecord.id == campaign_line_id).values(
        contracted_impressions=impressions, sale_cpm=Decimal(cpm)))
    session.execute(update(CampaignLinePeriodRecord).where(
        CampaignLinePeriodRecord.campaign_line_id == campaign_line_id).values(contracted_impressions=impressions))
    session.flush()


def flight_ids(session: Session, campaign_line_id: int) -> list[int]:
    return list(session.scalars(
        select(CampaignLinePeriodRecord.id)
        .where(CampaignLinePeriodRecord.campaign_line_id == campaign_line_id)
        .order_by(CampaignLinePeriodRecord.flight_start)
    ))
