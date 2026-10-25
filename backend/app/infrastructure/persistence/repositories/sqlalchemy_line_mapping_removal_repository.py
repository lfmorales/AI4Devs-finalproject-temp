from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from app.domain.repositories.line_mapping_removal_repository import LineMappingRemovalRepository
from app.infrastructure.persistence.models.campaign import CampaignLineRecord
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord
from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord


class SqlAlchemyLineMappingRemovalRepository(LineMappingRemovalRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def line_exists(self, campaign_line_id: int) -> bool:
        return bool(self._session.scalar(select(exists().where(CampaignLineRecord.id == campaign_line_id))))

    def mapping_ids(self, campaign_line_id: int) -> list[int]:
        return list(self._session.scalars(
            select(DSPMappingRecord.id).where(DSPMappingRecord.campaign_line_id == campaign_line_id)
        ))

    def delete_mapping(self, mapping_id: int) -> None:
        self._session.execute(delete(DSPMappingRecord).where(DSPMappingRecord.id == mapping_id))

    def delete_deliveries(self, campaign_line_id: int) -> int:
        result = self._session.execute(
            delete(DailyDeliveryRecord).where(DailyDeliveryRecord.campaign_line_id == campaign_line_id)
        )
        return int(result.rowcount)

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
