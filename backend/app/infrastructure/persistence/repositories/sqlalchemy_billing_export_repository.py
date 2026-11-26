from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.domain.repositories.billing_export_repository import BillingExportRepository
from app.domain.value_objects.billing import BillingBasis
from app.domain.value_objects.billing_export import ExportRow
from app.infrastructure.persistence.models.campaign import CampaignLinePeriodRecord, CampaignLineRecord, CampaignRecord
from app.infrastructure.persistence.models.margin import (
    AppliedRateRecord,
    ClosedFlightSnapshotRecord,
    FlightBillingAdjustmentRecord,
    MonthClosingRecord,
)
from app.infrastructure.persistence.models.masters import AdvertiserRecord, AgencyRecord
from app.infrastructure.persistence.models.purchase_order import PurchaseOrderRecord, PurchaseOrderVersionRecord


class SqlAlchemyBillingExportRepository(BillingExportRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def month_is_closed(self, year: int, month: int) -> bool:
        return bool(self._session.scalar(select(exists().where(
            MonthClosingRecord.period_year == year, MonthClosingRecord.period_month == month,
        ))))

    def frozen_rows(self, year: int, month: int) -> list[ExportRow]:
        snapshot = ClosedFlightSnapshotRecord
        flight = CampaignLinePeriodRecord
        line = CampaignLineRecord
        rows = self._session.execute(
            select(
                AdvertiserRecord.name, AgencyRecord.name, CampaignRecord.name, line.line_number,
                PurchaseOrderRecord.order_reference, snapshot.delivered, snapshot.contracted_impressions,
                snapshot.carryover, snapshot.billable, snapshot.sale_cpm, snapshot.revenue, snapshot.billing_basis,
                FlightBillingAdjustmentRecord.reason,
            )
            .select_from(snapshot)
            .join(MonthClosingRecord, MonthClosingRecord.id == snapshot.month_closing_id)
            .join(AppliedRateRecord, AppliedRateRecord.id == snapshot.applied_rate_id)
            .join(flight, flight.id == AppliedRateRecord.campaign_line_period_id)
            .join(line, line.id == flight.campaign_line_id)
            .join(CampaignRecord, CampaignRecord.id == line.campaign_id)
            .join(AgencyRecord, AgencyRecord.id == CampaignRecord.agency_id)
            .join(AdvertiserRecord, AdvertiserRecord.id == CampaignRecord.advertiser_id)
            .outerjoin(PurchaseOrderVersionRecord, PurchaseOrderVersionRecord.id == line.purchase_order_version_id)
            .outerjoin(PurchaseOrderRecord, PurchaseOrderRecord.id == PurchaseOrderVersionRecord.purchase_order_id)
            .outerjoin(FlightBillingAdjustmentRecord, FlightBillingAdjustmentRecord.id == snapshot.billing_adjustment_id)
            .where(MonthClosingRecord.period_year == year, MonthClosingRecord.period_month == month)
            .order_by(AgencyRecord.name, CampaignRecord.name, CampaignRecord.id, line.line_number, flight.flight_start,
                      flight.id)
        ).all()
        return [
            ExportRow(
                advertiser=advertiser, agency=agency, campaign=campaign, line_number=number, purchase_order=order,
                delivered=delivered, contracted=int(contracted), carryover=None if carryover is None else int(carryover),
                billable=billable, sale_cpm=cpm, revenue=revenue,
                billing_basis=None if basis is None else BillingBasis(basis), reason=reason,
            )
            for advertiser, agency, campaign, number, order, delivered, contracted, carryover, billable, cpm, revenue,
            basis, reason in rows
        ]
