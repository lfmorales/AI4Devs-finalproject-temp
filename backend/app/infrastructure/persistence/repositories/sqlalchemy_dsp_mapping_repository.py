from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.entities.dsp_mapping import DspMapping, LineDsp
from app.domain.exceptions import DuplicateDspMappingError
from app.domain.repositories.dsp_mapping_repository import DspMappingRepository
from app.domain.value_objects.delivery import ExternalLineKey
from app.infrastructure.persistence.models.campaign import CampaignLineRecord
from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord
from app.infrastructure.persistence.models.masters import DSPRecord


PAIR_CONSTRAINT = "uq_dsp_mappings_dsp_external_ids"


class SqlAlchemyDspMappingRepository(DspMappingRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_line_dsp(self, campaign_line_id: int) -> LineDsp | None:
        row = self._session.execute(
            select(DSPRecord.id, DSPRecord.name, CampaignLineRecord.start_date)
            .join(CampaignLineRecord, CampaignLineRecord.dsp_id == DSPRecord.id)
            .where(CampaignLineRecord.id == campaign_line_id)
        ).one_or_none()
        return None if row is None else LineDsp(dsp_id=row.id, dsp_name=row.name, line_start_date=row.start_date)

    def pair_exists(self, dsp_id: int, key: ExternalLineKey) -> bool:
        return bool(self._session.scalar(select(exists().where(
            DSPMappingRecord.dsp_id == dsp_id,
            DSPMappingRecord.external_campaign_id == key.external_campaign_id,
            DSPMappingRecord.external_line_item_id == key.external_line_item_id,
        ))))

    def add(
        self, campaign_line_id: int, dsp_id: int, key: ExternalLineKey, validated_at: datetime | None
    ) -> DspMapping:
        record = DSPMappingRecord(
            campaign_line_id=campaign_line_id,
            dsp_id=dsp_id,
            external_campaign_id=key.external_campaign_id,
            external_line_item_id=key.external_line_item_id,
            validated_at=validated_at,
        )
        self._session.add(record)
        try:
            self._session.flush()
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            # The unique constraint is the last word when two requests race past pair_exists.
            if getattr(error.orig.diag, "constraint_name", None) == PAIR_CONSTRAINT:  # type: ignore[union-attr]
                raise DuplicateDspMappingError("pair already mapped") from None
            raise
        return DspMapping(record.id, campaign_line_id, dsp_id, key, validated_at)
