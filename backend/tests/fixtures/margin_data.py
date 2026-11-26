"""Builders for the margin tests: schedules, volumes and deliveries on top of the delivery fixtures."""

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from app.application.services.monthly_review_service import MonthlyReviewService
from app.domain.value_objects.review import ReviewState
from app.infrastructure.persistence.models.delivery import IngestionBatchRecord
from app.infrastructure.persistence.repositories.sqlalchemy_review_repository import (
    SqlAlchemyMonthlyReviewTransaction,
)
from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
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


def load_months_last_day(session: Session, year: int, month: int) -> list[int]:
    """Record, for each DSP of the lines with flights in the month that has not loaded the month's last day, a succeeded
    batch whose window is that day, finished the next day; a DSP that has loaded it gets nothing. Returns the new
    batches' ids. Delivery is not touched: the batch only states that the day was loaded."""
    last_day = date(year, month, monthrange(year, month)[1])
    loaded = exists().where(
        IngestionBatchRecord.dsp_id == CampaignLineRecord.dsp_id,
        IngestionBatchRecord.status == "succeeded",
        IngestionBatchRecord.window_start <= last_day,
        IngestionBatchRecord.window_end >= last_day,
    )
    dsp_ids = session.scalars(
        select(CampaignLineRecord.dsp_id)
        .join(CampaignLinePeriodRecord, CampaignLinePeriodRecord.campaign_line_id == CampaignLineRecord.id)
        .join(CampaignPeriodRecord, CampaignPeriodRecord.id == CampaignLinePeriodRecord.campaign_period_id)
        .where(CampaignPeriodRecord.period_year == year, CampaignPeriodRecord.period_month == month, ~loaded)
        .distinct()
        .order_by(CampaignLineRecord.dsp_id)
    ).all()
    finished = datetime.combine(last_day + timedelta(days=1), datetime.min.time())
    batches = [
        IngestionBatchRecord(
            dsp_id=dsp_id, route="api", source_file=None, started_at=finished, finished_at=finished,
            status="succeeded", row_count=0, window_start=last_day, window_end=last_day,
        )
        for dsp_id in dsp_ids
    ]
    session.add_all(batches)
    session.flush()
    return [batch.id for batch in batches]


def review_month(session: Session, year: int, month: int, user_id: int, today: date) -> list[int]:
    """Mark reviewed, through the review service as of `today`, every campaign of the month pending review, and return
    their ids. A campaign in progress, already reviewed or closed is left as it is. The service commits, which commits
    what the test stored before it."""
    service = MonthlyReviewService(
        SqlAlchemyMonthlyReviewTransaction(session), today=lambda: today, now=lambda: datetime.combine(today, datetime.min.time()),
    )
    campaign_ids = session.scalars(
        select(CampaignPeriodRecord.campaign_id)
        .where(
            CampaignPeriodRecord.period_year == year, CampaignPeriodRecord.period_month == month,
            exists().where(CampaignLinePeriodRecord.campaign_period_id == CampaignPeriodRecord.id),
        )
        .order_by(CampaignPeriodRecord.campaign_id)
    ).all()
    reviewed = [
        campaign_id for campaign_id in campaign_ids
        if service.state(campaign_id, year, month) is ReviewState.PENDING_REVIEW
    ]
    for campaign_id in reviewed:
        service.review(campaign_id, year, month, user_id)
    return reviewed


MONTH_REVIEWER_EMAIL = "month-reviewer@example.com"


def month_reviewer(session: Session) -> int:
    """The user the closing tests review a month as when they name none: created on first use."""
    from app.infrastructure.persistence.models.identity import UserRecord

    user_id = session.scalar(select(UserRecord.id).where(UserRecord.email == MONTH_REVIEWER_EMAIL))
    if user_id is None:
        user = UserRecord(email=MONTH_REVIEWER_EMAIL, full_name="Month reviewer", is_active=True)
        session.add(user)
        session.flush()
        user_id = user.id
    return user_id


def make_month_closable(
    session: Session, year: int, month: int, user_id: int | None, today: date, load_last_day: bool = True
) -> None:
    """What every closing test does before it closes a month: its DSPs have loaded its last day (unless the test is
    about that refusal) and every campaign of it pending review is reviewed, by `user_id` or by the month reviewer."""
    if load_last_day:
        load_months_last_day(session, year, month)
    review_month(session, year, month, month_reviewer(session) if user_id is None else user_id, today)
