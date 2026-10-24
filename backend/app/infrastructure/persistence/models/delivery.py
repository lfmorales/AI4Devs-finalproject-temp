"""Delivery ingestion: daily deliveries, the batches that produced them, and unmatched-key exceptions."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.base import Base


class IngestionBatchRecord(Base):
    """One ingestion run, whatever route it arrived by."""

    __tablename__ = "ingestion_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    dsp_id: Mapped[int] = mapped_column(ForeignKey("dsps.id"), nullable=False, index=True)
    route: Mapped[str] = mapped_column(SQLEnum("api", "upload", "email", name="ingestion_route_enum"), nullable=False)
    source_file: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        SQLEnum("running", "succeeded", "failed", name="ingestion_batch_status_enum"), nullable=False
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Rows the DSP reported without an attributed line item; counted, never worked as exceptions.
    ignored_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class DailyDeliveryRecord(Base):
    """Delivered volume for one campaign line and one calendar day. The high-volume table."""

    __tablename__ = "daily_deliveries"
    __table_args__ = (
        # One row per line and day: the replace-then-insert ingestion relies on this grain.
        UniqueConstraint("campaign_line_id", "delivery_date", name="uq_daily_deliveries_line_date"),
        # Period roll-ups filter on the date range first, then join through the line.
        Index("ix_daily_deliveries_delivery_date", "delivery_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    campaign_line_id: Mapped[int] = mapped_column(ForeignKey("campaign_lines.id"), nullable=False)
    ingestion_batch_id: Mapped[int] = mapped_column(ForeignKey("ingestion_batches.id"), nullable=False, index=True)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_cost: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=6), nullable=False)
    measurable_impressions: Mapped[int] = mapped_column(BigInteger, nullable=False)
    viewable_impressions: Mapped[int] = mapped_column(BigInteger, nullable=False)
    banner_size: Mapped[str | None] = mapped_column(String, nullable=True)
    screen: Mapped[str | None] = mapped_column(String, nullable=True)
    # Contrast data only: no calculation reads it. The configured channel is authoritative.
    line_format: Mapped[str | None] = mapped_column(String, nullable=True)


class IngestionExceptionRecord(Base):
    """An unmatched key, or a channel disagreement, waiting to be worked."""

    __tablename__ = "ingestion_exceptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    ingestion_batch_id: Mapped[int] = mapped_column(ForeignKey("ingestion_batches.id"), nullable=False, index=True)
    campaign_line_id: Mapped[int | None] = mapped_column(ForeignKey("campaign_lines.id"), nullable=True)
    exception_type: Mapped[str] = mapped_column(
        SQLEnum(
            "delivery_without_line",
            "line_without_delivery",
            "channel_mismatch",
            name="ingestion_exception_type_enum",
        ),
        nullable=False,
    )
    external_key: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        SQLEnum("open", "resolved", name="ingestion_exception_status_enum"), nullable=False, default="open"
    )
