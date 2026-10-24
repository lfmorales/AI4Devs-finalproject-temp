"""Delivery ingestion: daily deliveries, the batches that produced them, and unmatched-key exceptions."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
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
    # Unmatched rows with no impressions and no cost: the statistics API returns many for active campaigns.
    zero_unmatched_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


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
    """Something to work: delivery that matched no line, a line that delivered nothing, or a channel mismatch."""

    __tablename__ = "ingestion_exceptions"
    __table_args__ = (
        CheckConstraint(
            "exception_type <> 'unmatched_delivery' OR (dsp_id IS NOT NULL AND external_campaign_id IS NOT NULL "
            "AND external_line_item_id IS NOT NULL)",
            name="ck_ingestion_exceptions_unmatched_fields",
        ),
        CheckConstraint(
            "exception_type <> 'missing_delivery' OR (campaign_line_id IS NOT NULL AND campaign_period_id IS NOT NULL)",
            name="ck_ingestion_exceptions_missing_fields",
        ),
        CheckConstraint(
            "(status = 'open' AND resolved_at IS NULL AND resolved_by IS NULL) OR "
            "(status = 'resolved' AND resolved_at IS NOT NULL AND resolved_by IS NOT NULL)",
            name="ck_ingestion_exceptions_resolution_fields",
        ),
        # One exception per DSP and pair whatever its status: a resolved pair that delivers again is not reopened.
        Index(
            "uq_ingestion_exceptions_unmatched_pair",
            "exception_type", "dsp_id", "external_campaign_id", "external_line_item_id",
            unique=True,
            postgresql_where=text("exception_type = 'unmatched_delivery'"),
        ),
        Index(
            "uq_ingestion_exceptions_missing_line_period",
            "campaign_line_id", "campaign_period_id",
            unique=True,
            postgresql_where=text("exception_type = 'missing_delivery'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # The batch that first raised it.
    ingestion_batch_id: Mapped[int] = mapped_column(ForeignKey("ingestion_batches.id"), nullable=False, index=True)
    exception_type: Mapped[str] = mapped_column(
        SQLEnum(
            "unmatched_delivery",
            "missing_delivery",
            "channel_mismatch",
            name="ingestion_exception_type_enum",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        SQLEnum("open", "resolved", name="ingestion_exception_status_enum"), nullable=False, default="open"
    )
    campaign_line_id: Mapped[int | None] = mapped_column(ForeignKey("campaign_lines.id"), nullable=True)
    campaign_period_id: Mapped[int | None] = mapped_column(ForeignKey("campaign_periods.id"), nullable=True)
    dsp_id: Mapped[int | None] = mapped_column(ForeignKey("dsps.id"), nullable=True)
    external_campaign_id: Mapped[str | None] = mapped_column(String, nullable=True)
    external_line_item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    first_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)


class IngestionExceptionDeliveryRecord(Base):
    """Delivery retained for an unmatched pair, one row per date. Resolving the exception never moves it."""

    __tablename__ = "ingestion_exception_deliveries"
    __table_args__ = (UniqueConstraint("exception_id", "delivery_date", name="uq_exception_deliveries_exception_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    exception_id: Mapped[int] = mapped_column(ForeignKey("ingestion_exceptions.id"), nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_cost: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=6), nullable=False)
    measurable_impressions: Mapped[int] = mapped_column(BigInteger, nullable=False)
    viewable_impressions: Mapped[int] = mapped_column(BigInteger, nullable=False)
