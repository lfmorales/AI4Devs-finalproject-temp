"""What a DSP says about its line items, kept by the ingestion so operations can pick a pair to map."""

from datetime import date

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.base import Base


class DspCatalogLineRecord(Base):
    __tablename__ = "dsp_catalog_lines"
    __table_args__ = (
        UniqueConstraint(
            "dsp_id", "external_campaign_id", "external_line_item_id", name="uq_dsp_catalog_lines_dsp_external_ids"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dsp_id: Mapped[int] = mapped_column(ForeignKey("dsps.id"), nullable=False)
    external_campaign_id: Mapped[str] = mapped_column(String, nullable=False)
    external_line_item_id: Mapped[str] = mapped_column(String, nullable=False)
    campaign_name: Mapped[str] = mapped_column(String, nullable=False)
    line_item_name: Mapped[str] = mapped_column(String, nullable=False)
    line_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    line_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # The oldest and the latest delivery date with a row in the DSP: not real activity.
    first_seen_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_seen_date: Mapped[date] = mapped_column(Date, nullable=False)
    # The latest delivery date with impressions above zero; null when the pair has only delivered zeros.
    last_impressions_date: Mapped[date | None] = mapped_column(Date, nullable=True)
