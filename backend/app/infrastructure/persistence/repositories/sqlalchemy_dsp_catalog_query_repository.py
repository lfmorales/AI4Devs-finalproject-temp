from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.entities.dsp_catalog import CatalogLineSummary, CatalogPage, CatalogQuery
from app.domain.repositories.dsp_catalog_query_repository import DspCatalogQueryRepository
from app.infrastructure.persistence.models.dsp_catalog import DspCatalogLineRecord
from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord


class SqlAlchemyDspCatalogQueryRepository(DspCatalogQueryRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def search(self, query: CatalogQuery) -> CatalogPage:
        line, mapping = DspCatalogLineRecord, DSPMappingRecord
        # A pair maps to at most one line (unique on DSP and pair), so the join never repeats a catalogue row.
        source = select(line, mapping.campaign_line_id.label("mapped_line_id")).outerjoin(
            mapping,
            (mapping.dsp_id == line.dsp_id)
            & (mapping.external_campaign_id == line.external_campaign_id)
            & (mapping.external_line_item_id == line.external_line_item_id),
        )
        if query.dsp_id is not None:
            source = source.where(line.dsp_id == query.dsp_id)
        if query.text:
            pattern = "%" + _escape_like(query.text) + "%"
            source = source.where(
                line.campaign_name.ilike(pattern, escape="\\") | line.line_item_name.ilike(pattern, escape="\\")
            )
        if query.mapped is True:
            source = source.where(mapping.id.is_not(None))
        elif query.mapped is False:
            source = source.where(mapping.id.is_(None))
        if query.active_since is not None:
            source = source.where(line.last_seen_date >= query.active_since)

        total = self._session.scalar(select(func.count()).select_from(source.subquery())) or 0
        rows = self._session.execute(
            source.order_by(line.last_seen_date.desc(), line.id).limit(query.limit).offset(query.offset)
        )
        return CatalogPage([_to_summary(row[0], row.mapped_line_id) for row in rows], int(total))


def _escape_like(text: str) -> str:
    """The text as a literal inside a LIKE pattern: the user's % and _ are not wildcards."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _to_summary(record: DspCatalogLineRecord, mapped_line_id: int | None) -> CatalogLineSummary:
    return CatalogLineSummary(
        dsp_id=record.dsp_id,
        external_campaign_id=record.external_campaign_id,
        external_line_item_id=record.external_line_item_id,
        campaign_name=record.campaign_name,
        line_item_name=record.line_item_name,
        line_start_date=record.line_start_date,
        line_end_date=record.line_end_date,
        first_seen_date=record.first_seen_date,
        last_seen_date=record.last_seen_date,
        last_impressions_date=record.last_impressions_date,
        mapped_line_id=mapped_line_id,
    )
