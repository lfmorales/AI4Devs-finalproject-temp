from datetime import date, timedelta

from sqlalchemy import Date, and_, cast, exists, func, select
from sqlalchemy.orm import Session

from app.domain.repositories.ingestion_target_repository import IngestionTargetRepository
from app.domain.value_objects.delivery import DeliveryDateRange, ExternalLineKey
from app.domain.value_objects.ingestion import IngestionTargets, MappedLine, MissingDeliveryCandidate
from app.infrastructure.persistence.models.campaign import (
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
)
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord
from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord


class SqlAlchemyIngestionTargetRepository(IngestionTargetRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_targets(self, dsp_id: int, window: DeliveryDateRange) -> IngestionTargets:
        # Status is deliberately not filtered: a campaign that ended days ago still has figures the DSP restates.
        # The outer join keeps a line with no validated mapping for this DSP, which is how it is counted as skipped.
        validated_mapping = and_(
            DSPMappingRecord.campaign_line_id == CampaignLineRecord.id,
            DSPMappingRecord.dsp_id == dsp_id,
            DSPMappingRecord.validated_at.is_not(None),
        )
        rows = self._session.execute(
            select(
                CampaignLineRecord.id,
                DSPMappingRecord.external_campaign_id,
                DSPMappingRecord.external_line_item_id,
            )
            .select_from(CampaignLineRecord)
            .join(CampaignPeriodRecord, CampaignPeriodRecord.id == CampaignLineRecord.campaign_period_id)
            .join(CampaignRecord, CampaignRecord.id == CampaignPeriodRecord.campaign_id)
            .outerjoin(DSPMappingRecord, validated_mapping)
            .where(
                CampaignLineRecord.dsp_id == dsp_id,
                CampaignRecord.start_date <= window.end,
                CampaignRecord.end_date >= window.start,
            )
            .order_by(
                CampaignLineRecord.id,
                DSPMappingRecord.external_campaign_id,
                DSPMappingRecord.external_line_item_id,
            )
        ).all()

        mapped_lines: list[MappedLine] = []
        unmapped_line_ids: list[int] = []
        for line_id, external_campaign_id, external_line_item_id in rows:
            if external_campaign_id is None or external_line_item_id is None:
                unmapped_line_ids.append(line_id)
            else:
                mapped_lines.append(
                    MappedLine(line_id, ExternalLineKey.from_raw(external_campaign_id, external_line_item_id))
                )
        return IngestionTargets(tuple(mapped_lines), tuple(unmapped_line_ids))

    def find_watched_campaign_ids(self, today: date) -> tuple[int, ...]:
        # Narrower than the ingestion set on purpose: an ended campaign is still ingested to pick up restated
        # figures, but it is no longer expected to deliver, so it must not raise a missing-data flag.
        day_before = today - timedelta(days=1)
        return tuple(self._session.scalars(
            select(CampaignRecord.id)
            .where(
                CampaignRecord.status == "active",
                CampaignRecord.start_date <= day_before,
                CampaignRecord.end_date >= day_before,
            )
            .order_by(CampaignRecord.id)
        ))

    def find_lines_missing_delivery(self, dsp_id: int, window: DeliveryDateRange) -> tuple[MissingDeliveryCandidate, ...]:
        period = CampaignPeriodRecord
        # Summed in the database over the whole period, including days older than the ingestion window.
        impressions_in_period = (
            select(func.coalesce(func.sum(DailyDeliveryRecord.impressions), 0))
            .where(
                DailyDeliveryRecord.campaign_line_id == CampaignLineRecord.id,
                DailyDeliveryRecord.delivery_date.between(period.period_start, period.period_end),
            )
            .scalar_subquery()
        )
        # Compared as dates: a mapping validated at 15:30 on the last day still covers that day.
        mapped_by_period_end = exists().where(
            DSPMappingRecord.campaign_line_id == CampaignLineRecord.id,
            DSPMappingRecord.dsp_id == dsp_id,
            DSPMappingRecord.validated_at.is_not(None),
            cast(DSPMappingRecord.validated_at, Date) <= period.period_end,
        )
        rows = self._session.execute(
            select(CampaignLineRecord.id, period.id)
            .join(period, period.id == CampaignLineRecord.campaign_period_id)
            .where(
                CampaignLineRecord.dsp_id == dsp_id,
                period.period_end.between(window.start, window.end),
                mapped_by_period_end,
                impressions_in_period == 0,
            )
            .order_by(CampaignLineRecord.id, period.id)
        ).all()
        return tuple(MissingDeliveryCandidate(line_id, period_id) for line_id, period_id in rows)
