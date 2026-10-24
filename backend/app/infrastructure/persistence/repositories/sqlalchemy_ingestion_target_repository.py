from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.domain.repositories.ingestion_target_repository import IngestionTargetRepository
from app.domain.value_objects.delivery import DeliveryDateRange, ExternalLineKey
from app.domain.value_objects.ingestion import IngestionTargets, MappedLine
from app.infrastructure.persistence.models.campaign import (
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
)
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
