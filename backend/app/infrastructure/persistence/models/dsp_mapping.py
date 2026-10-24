"""DSP mapping: external IDs that bind campaign lines to DSPs."""

from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.base import Base


class DSPMappingRecord(Base):
    __tablename__ = "dsp_mappings"
    __table_args__ = (
        # Ingestion resolves a DSP's external identifiers to a campaign line through this key.
        Index("ix_dsp_mappings_dsp_external_ids", "dsp_id", "external_campaign_id", "external_line_item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_line_id: Mapped[int] = mapped_column(ForeignKey("campaign_lines.id"), nullable=False, index=True)
    dsp_id: Mapped[int] = mapped_column(ForeignKey("dsps.id"), nullable=False)
    external_campaign_id: Mapped[str] = mapped_column(String, nullable=False)
    external_line_item_id: Mapped[str] = mapped_column(String, nullable=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
