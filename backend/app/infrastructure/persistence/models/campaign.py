"""Campaign tree: campaigns, campaign periods, and campaign lines."""

from datetime import date, datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, ForeignKey, Date, BigInteger, Text, UniqueConstraint, Enum as SQLEnum
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
        # Kept as the partial index the additive migration created; with both columns mandatory it covers every row.
        Index(
            "uq_campaign_lines_campaign_line_number", "campaign_id", "line_number", unique=True,
            postgresql_where=text("campaign_id IS NOT NULL AND line_number IS NOT NULL"),
        ),
        CheckConstraint(
            "volume_commitment IN ('committed', 'target')", name="ck_campaign_lines_volume_commitment"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # A line hangs from its campaign, numbered within it, with its own dates. Its months are its flights.
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    line_number: Mapped[int] = mapped_column(nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    purchase_order_version_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_order_versions.id"), nullable=True)
    dsp_id: Mapped[int] = mapped_column(ForeignKey("dsps.id"), nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    format_id: Mapped[int] = mapped_column(ForeignKey("formats.id"), nullable=False)
    scope: Mapped[str] = mapped_column(SQLEnum("national", "international", name="scope_enum"), nullable=False)
    market_description: Mapped[str] = mapped_column(String, nullable=False)
    contracted_impressions: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sale_cpm: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="EUR")
    # committed: the buyer committed to the volume; target: the volume is an objective. Never derived from the channel.
    volume_commitment: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'committed'"))


class CampaignLinePeriodRecord(Base):
    """A flight: the volume of one line in one calendar month, over the days the two share."""

    __tablename__ = "campaign_line_periods"
    __table_args__ = (
        UniqueConstraint("campaign_line_id", "campaign_period_id", name="uq_campaign_line_periods_line_period"),
        CheckConstraint("flight_start <= flight_end", name="ck_campaign_line_periods_window_order"),
        CheckConstraint("carryover >= 0", name="ck_campaign_line_periods_carryover_not_negative"),
        # A carry-over is written with its reason, its author and its moment; a removed one (0) may keep them.
        CheckConstraint(
            "carryover = 0 OR (carryover_reason IS NOT NULL AND length(btrim(carryover_reason)) > 0"
            " AND carryover_set_by IS NOT NULL AND carryover_set_at IS NOT NULL)",
            name="ck_campaign_line_periods_carryover_is_accounted_for",
        ),
        CheckConstraint(
            "NOT carryover_billable OR (carryover_billable_set_by IS NOT NULL AND carryover_billable_set_at IS NOT NULL)",
            name="ck_campaign_line_periods_carryover_billable_is_accounted_for",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_line_id: Mapped[int] = mapped_column(ForeignKey("campaign_lines.id"), nullable=False)
    campaign_period_id: Mapped[int] = mapped_column(ForeignKey("campaign_periods.id"), nullable=False, index=True)
    flight_start: Mapped[date] = mapped_column(Date, nullable=False)
    flight_end: Mapped[date] = mapped_column(Date, nullable=False)
    contracted_impressions: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # The volume carried to this flight from the previous flight of its line, in the unit of the line's delivery metric.
    # It never changes `contracted_impressions`: the delivery target is the two added (campaign/carryover).
    carryover: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    carryover_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    carryover_set_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    carryover_set_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Whether the carry-over raises the cap of the flight's billing; set only by operations or finance.
    carryover_billable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    carryover_billable_set_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    carryover_billable_set_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
