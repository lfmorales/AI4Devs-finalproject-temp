from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.domain.entities.unmapped_line import UnmappedLine
from app.domain.repositories.campaign_line_query_repository import CampaignLineQueryRepository
from app.infrastructure.persistence.models.campaign import CampaignLineRecord, CampaignRecord
from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord
from app.infrastructure.persistence.models.masters import DSPRecord


class SqlAlchemyCampaignLineQueryRepository(CampaignLineQueryRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_unmapped(self) -> list[UnmappedLine]:
        line = CampaignLineRecord
        rows = self._session.execute(
            select(line.id, CampaignRecord.name, line.line_number, line.start_date, line.end_date, DSPRecord.id, DSPRecord.name)
            .join(CampaignRecord, CampaignRecord.id == line.campaign_id)
            .join(DSPRecord, DSPRecord.id == line.dsp_id)
            .where(~exists().where(DSPMappingRecord.campaign_line_id == line.id))
            .order_by(CampaignRecord.name, line.line_number, line.id)
        )
        return [UnmappedLine(*row) for row in rows]
