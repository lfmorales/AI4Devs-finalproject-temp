from collections.abc import Iterable

from sqlalchemy import case, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.repositories.dsp_catalog_repository import DspCatalogRepository
from app.domain.value_objects.catalog import CatalogLineObservation
from app.infrastructure.persistence.models.dsp_catalog import DspCatalogLineRecord

_BATCH_SIZE = 1000


class SqlAlchemyDspCatalogRepository(DspCatalogRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_all(self, dsp_id: int, observations: Iterable[CatalogLineObservation]) -> None:
        values = [
            {
                "dsp_id": dsp_id,
                "external_campaign_id": observation.key.external_campaign_id,
                "external_line_item_id": observation.key.external_line_item_id,
                "campaign_name": observation.campaign_name,
                "line_item_name": observation.line_item_name,
                "line_start_date": observation.line_start_date,
                "line_end_date": observation.line_end_date,
                "first_seen_date": observation.first_seen_date,
                "last_seen_date": observation.last_seen_date,
                "last_impressions_date": observation.last_impressions_date,
            }
            for observation in observations
        ]
        for start in range(0, len(values), _BATCH_SIZE):
            self._session.execute(self._upsert(values[start:start + _BATCH_SIZE]))

    @staticmethod
    def _upsert(values: list[dict]):  # type: ignore[no-untyped-def]
        table = DspCatalogLineRecord.__table__
        statement = insert(table).values(values)
        incoming = statement.excluded
        # The same rule as CatalogLineObservation.merged_into: dates widen; names and dates follow the newer side.
        newer = incoming.last_seen_date >= table.c.last_seen_date

        def follow_newer(column: str):  # type: ignore[no-untyped-def]
            return case((newer, incoming[column]), else_=table.c[column])

        return statement.on_conflict_do_update(
            constraint="uq_dsp_catalog_lines_dsp_external_ids",
            set_={
                "campaign_name": follow_newer("campaign_name"),
                "line_item_name": follow_newer("line_item_name"),
                "line_start_date": follow_newer("line_start_date"),
                "line_end_date": follow_newer("line_end_date"),
                "first_seen_date": func.least(table.c.first_seen_date, incoming.first_seen_date),
                "last_seen_date": func.greatest(table.c.last_seen_date, incoming.last_seen_date),
                # GREATEST ignores nulls in PostgreSQL: null only when both sides are null.
                "last_impressions_date": func.greatest(table.c.last_impressions_date, incoming.last_impressions_date),
            },
        )
