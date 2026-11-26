from datetime import date
from typing import Any

from sqlalchemy import ScalarSelect, case, exists, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.domain.repositories.billing_read_repository import BillingReadRepository, MonthCampaignRow, MonthFlightRow
from app.domain.services.monthly_review import FlightCounts
from app.domain.value_objects.review import ReviewKind
from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
)
from app.infrastructure.persistence.models.margin import (
    AppliedRateRecord,
    CampaignPeriodReviewRecord,
    ClosedFlightSnapshotRecord,
    FlightBillingAdjustmentRecord,
)
from app.infrastructure.persistence.models.masters import AdvertiserRecord, AgencyRecord, ChannelRecord
from app.infrastructure.persistence.repositories.sqlalchemy_billing_adjustment_repository import _entry


class SqlAlchemyBillingReadRepository(BillingReadRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def campaign_exists(self, campaign_id: int) -> bool:
        return bool(self._session.scalar(select(exists().where(CampaignRecord.id == campaign_id))))

    def month_campaigns(
        self, year: int, month: int, as_of: date, campaign_id: int | None = None
    ) -> list[MonthCampaignRow]:
        flight = CampaignLinePeriodRecord
        period = CampaignPeriodRecord
        frozen = exists().where(AppliedRateRecord.campaign_line_period_id == flight.id)

        def latest(column: InstrumentedAttribute[Any]) -> ScalarSelect[Any]:
            return (
                select(column).where(CampaignPeriodReviewRecord.campaign_period_id == period.id)
                .order_by(CampaignPeriodReviewRecord.id.desc()).limit(1).scalar_subquery()
            )

        query = (
            select(
                CampaignRecord.id, CampaignRecord.name, AgencyRecord.name, AdvertiserRecord.name,
                func.count(), func.count().filter(flight.flight_end <= as_of), func.count().filter(frozen),
                latest(CampaignPeriodReviewRecord.kind), latest(CampaignPeriodReviewRecord.created_by),
                latest(CampaignPeriodReviewRecord.created_at),
            )
            .select_from(flight)
            .join(period, period.id == flight.campaign_period_id)
            .join(CampaignRecord, CampaignRecord.id == period.campaign_id)
            .join(AgencyRecord, AgencyRecord.id == CampaignRecord.agency_id)
            .join(AdvertiserRecord, AdvertiserRecord.id == CampaignRecord.advertiser_id)
            .where(period.period_year == year, period.period_month == month)
            .group_by(CampaignRecord.id, CampaignRecord.name, AgencyRecord.name, AdvertiserRecord.name, period.id)
            .order_by(CampaignRecord.name, CampaignRecord.id)
        )
        if campaign_id is not None:
            query = query.where(CampaignRecord.id == campaign_id)
        return [
            MonthCampaignRow(
                campaign_id=row_id, name=name, agency=agency, advertiser=advertiser,
                counts=FlightCounts(total=int(total), ended=int(ended), frozen=int(frozen_count)),
                latest_kind=None if kind is None else ReviewKind(kind), latest_by=by, latest_at=at,
            )
            for row_id, name, agency, advertiser, total, ended, frozen_count, kind, by, at
            in self._session.execute(query).all()
        ]

    def month_flights(self, year: int, month: int, campaign_id: int | None = None) -> list[MonthFlightRow]:
        flight = CampaignLinePeriodRecord
        line = CampaignLineRecord
        snapshot = ClosedFlightSnapshotRecord
        applied = AppliedRateRecord
        is_frozen = applied.id.is_not(None)
        latest_adjustment = (
            select(FlightBillingAdjustmentRecord.id)
            .where(FlightBillingAdjustmentRecord.campaign_line_period_id == flight.id)
            .order_by(FlightBillingAdjustmentRecord.id.desc()).limit(1).scalar_subquery()
        )
        # A closed flight is read from its snapshot; any other from the line and the flight as stored now.
        query = (
            select(
                flight.id, CampaignPeriodRecord.campaign_id, line.id, line.line_number, flight.flight_start,
                flight.flight_end,
                case((is_frozen, snapshot.contracted_impressions), else_=flight.contracted_impressions),
                case((is_frozen, snapshot.delivery_metric), else_=ChannelRecord.delivery_metric),
                case((is_frozen, snapshot.sale_cpm), else_=line.sale_cpm),
                case((is_frozen, snapshot.carryover), else_=flight.carryover),
                case((is_frozen, snapshot.carryover_billable), else_=flight.carryover_billable),
                case((is_frozen, snapshot.billing_adjustment_id), else_=latest_adjustment),
            )
            .select_from(flight)
            .join(line, line.id == flight.campaign_line_id)
            .join(ChannelRecord, ChannelRecord.id == line.channel_id)
            .join(CampaignPeriodRecord, CampaignPeriodRecord.id == flight.campaign_period_id)
            .outerjoin(applied, applied.campaign_line_period_id == flight.id)
            .outerjoin(snapshot, snapshot.applied_rate_id == applied.id)
            .where(CampaignPeriodRecord.period_year == year, CampaignPeriodRecord.period_month == month)
            .order_by(line.line_number, flight.flight_start, flight.id)
        )
        if campaign_id is not None:
            query = query.where(CampaignPeriodRecord.campaign_id == campaign_id)
        rows = self._session.execute(query).all()
        adjustment_ids = [row[11] for row in rows if row[11] is not None]
        entries = {
            record.id: _entry(record)
            for record in self._session.scalars(
                select(FlightBillingAdjustmentRecord).where(FlightBillingAdjustmentRecord.id.in_(adjustment_ids))
            )
        } if adjustment_ids else {}
        return [
            MonthFlightRow(
                flight_id=flight_id, campaign_id=owner, campaign_line_id=line_id, line_number=number,
                flight_start=start, flight_end=end, contracted_impressions=int(contracted), delivery_metric=metric,
                sale_cpm=cpm, carryover=None if carryover is None else int(carryover), carryover_billable=billable,
                adjustment=None if adjustment_id is None else entries[adjustment_id],
            )
            for flight_id, owner, line_id, number, start, end, contracted, metric, cpm, carryover, billable, adjustment_id
            in rows
        ]
