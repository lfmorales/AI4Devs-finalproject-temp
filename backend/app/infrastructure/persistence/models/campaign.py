"""Campaign tree: campaigns, campaign periods, and campaign lines."""

from datetime import date
from sqlalchemy import CheckConstraint, Index, String, ForeignKey, Date, BigInteger, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal
from sqlalchemy import Numeric, text

from app.infrastructure.persistence.base import Base


class CampaignRecord(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agencies.id"), nullable=False, index=True)
    advertiser_id: Mapped[int] = mapped_column(ForeignKey("advertisers.id"), nullable=False)
    campaign_type_id: Mapped[int] = mapped_column(ForeignKey("campaign_types.id"), nullable=False)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id"), nullable=False)
    sales_rep_id: Mapped[int] = mapped_column(ForeignKey("sales_reps.id"), nullable=False)
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)


class CampaignPeriodRecord(Base):
    __tablename__ = "campaign_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    period_year: Mapped[int] = mapped_column(nullable=False)
    period_month: Mapped[int] = mapped_column(nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")


class CampaignLineRecord(Base):
    __tablename__ = "campaign_lines"
    __table_args__ = (
        # Nullable while the line still hangs from a period; only lines that have both are held to it.
        Index(
            "uq_campaign_lines_campaign_line_number", "campaign_id", "line_number", unique=True,
            postgresql_where=text("campaign_id IS NOT NULL AND line_number IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_period_id: Mapped[int] = mapped_column(ForeignKey("campaign_periods.id"), nullable=False, index=True)
    # The line is moving under its campaign: these stay empty until the registration writes them.
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    line_number: Mapped[int | None] = mapped_column(nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_order_version_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_order_versions.id"), nullable=True)
    dsp_id: Mapped[int] = mapped_column(ForeignKey("dsps.id"), nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    format_id: Mapped[int] = mapped_column(ForeignKey("formats.id"), nullable=False)
    scope: Mapped[str] = mapped_column(SQLEnum("national", "international", name="scope_enum"), nullable=False)
    market_description: Mapped[str] = mapped_column(String, nullable=False)
    contracted_impressions: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sale_cpm: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="EUR")


class CampaignLinePeriodRecord(Base):
    """A flight: the volume of one line in one calendar month, over the days the two share."""

    __tablename__ = "campaign_line_periods"
    __table_args__ = (
        UniqueConstraint("campaign_line_id", "campaign_period_id", name="uq_campaign_line_periods_line_period"),
        CheckConstraint("flight_start <= flight_end", name="ck_campaign_line_periods_window_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_line_id: Mapped[int] = mapped_column(ForeignKey("campaign_lines.id"), nullable=False)
    campaign_period_id: Mapped[int] = mapped_column(ForeignKey("campaign_periods.id"), nullable=False, index=True)
    flight_start: Mapped[date] = mapped_column(Date, nullable=False)
    flight_end: Mapped[date] = mapped_column(Date, nullable=False)
    contracted_impressions: Mapped[int] = mapped_column(BigInteger, nullable=False)
