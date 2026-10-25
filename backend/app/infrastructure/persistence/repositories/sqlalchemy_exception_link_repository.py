from datetime import datetime

from sqlalchemy import exists, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.entities.dsp_mapping import DspMapping, LineDsp
from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionType
from app.domain.exceptions import MappingPairTakenError
from app.domain.repositories.exception_link_repository import ExceptionLinkRepository, LinkableException
from app.domain.value_objects.delivery import ExternalLineKey
from app.infrastructure.persistence.models.campaign import CampaignLineRecord
from app.infrastructure.persistence.models.delivery import IngestionExceptionRecord
from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord
from app.infrastructure.persistence.models.masters import DSPRecord
from app.infrastructure.persistence.repositories.sqlalchemy_dsp_mapping_repository import PAIR_CONSTRAINT


class SqlAlchemyExceptionLinkRepository(ExceptionLinkRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_exception(self, exception_id: int) -> LinkableException | None:
        record = self._session.get(IngestionExceptionRecord, exception_id)
        if record is None:
            return None
        key = None
        if record.external_campaign_id is not None and record.external_line_item_id is not None:
            key = ExternalLineKey(record.external_campaign_id, record.external_line_item_id)
        return LinkableException(
            record.id, ExceptionType(record.exception_type), ExceptionStatus(record.status), record.dsp_id, key
        )

    def get_line(self, campaign_line_id: int) -> LineDsp | None:
        row = self._session.execute(
            select(DSPRecord.id, DSPRecord.name, CampaignLineRecord.start_date)
            .join(CampaignLineRecord, CampaignLineRecord.dsp_id == DSPRecord.id)
            .where(CampaignLineRecord.id == campaign_line_id)
        ).one_or_none()
        return None if row is None else LineDsp(row.id, row.name, row.start_date)

    def pair_exists(self, dsp_id: int, key: ExternalLineKey) -> bool:
        return bool(self._session.scalar(select(exists().where(
            DSPMappingRecord.dsp_id == dsp_id,
            DSPMappingRecord.external_campaign_id == key.external_campaign_id,
            DSPMappingRecord.external_line_item_id == key.external_line_item_id,
        ))))

    def add_mapping(
        self, campaign_line_id: int, dsp_id: int, key: ExternalLineKey, validated_at: datetime
    ) -> DspMapping:
        record = DSPMappingRecord(
            campaign_line_id=campaign_line_id, dsp_id=dsp_id, external_campaign_id=key.external_campaign_id,
            external_line_item_id=key.external_line_item_id, validated_at=validated_at,
        )
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as error:
            # The unique constraint is the last word when two requests race past pair_exists.
            if getattr(error.orig.diag, "constraint_name", None) == PAIR_CONSTRAINT:  # type: ignore[union-attr]
                raise MappingPairTakenError("pair already mapped") from None
            raise
        return DspMapping(record.id, campaign_line_id, dsp_id, key, validated_at)

    def resolve(self, exception_id: int, resolved_at: datetime, resolved_by: int, note: str) -> bool:
        result = self._session.execute(
            update(IngestionExceptionRecord)
            .where(IngestionExceptionRecord.id == exception_id, IngestionExceptionRecord.status == "open")
            .values(status="resolved", resolved_at=resolved_at, resolved_by=resolved_by, note=note)
        )
        return result.rowcount == 1

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
