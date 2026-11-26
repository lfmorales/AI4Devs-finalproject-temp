"""Margin tables: rebate schedules and brackets, platform rate settings, the rates frozen at closing, and the closing
headers with the snapshot of every closed flight."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.base import Base

# The type created for campaign_lines.scope; the schedules reuse it and never create it.
_SCOPE = ENUM("national", "international", name="scope_enum", create_type=False)

# Amounts and positions are revenue-sized with up to twelve decimals (an amount times a rate); rates likewise.
_AMOUNT = Numeric(24, 12)
_RATE = Numeric(20, 12)


class RebateScheduleRecord(Base):
    """A bracket table with validity. An agency exception names its agency; empty channel and scope mean any."""

    __tablename__ = "rebate_schedules"
    __table_args__ = (
        CheckConstraint("valid_to IS NULL OR valid_from <= valid_to", name="ck_rebate_schedules_validity_order"),
        # Two schedules of one key never overlap. valid_to is inclusive and an absent one is open-ended; the
        # optional parts of the key are folded to a value so that NULL equals NULL (an enum cast to text is not
        # immutable, so the scope is compared as a null flag plus the enum itself).
        ExcludeConstraint(
            ("holding_group_id", "="),
            (text("coalesce(agency_id, 0)"), "="),
            (text("coalesce(channel_id, 0)"), "="),
            (text("(scope IS NULL)"), "="),
            (text("coalesce(scope, 'national'::scope_enum)"), "="),
            (text("daterange(valid_from, valid_to, '[]')"), "&&"),
            using="gist",
            name="ex_rebate_schedules_key_validity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    holding_group_id: Mapped[int] = mapped_column(ForeignKey("holding_groups.id"), nullable=False)
    agency_id: Mapped[int | None] = mapped_column(ForeignKey("agencies.id"), nullable=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    scope: Mapped[str | None] = mapped_column(_SCOPE, nullable=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class RebateBracketRecord(Base):
    __tablename__ = "rebate_brackets"
    __table_args__ = (
        UniqueConstraint("rebate_schedule_id", "position", name="uq_rebate_brackets_schedule_position"),
        CheckConstraint("lower >= 0", name="ck_rebate_brackets_lower_not_negative"),
        CheckConstraint("upper IS NULL OR upper > lower", name="ck_rebate_brackets_upper_above_lower"),
        CheckConstraint("rate >= 0", name="ck_rebate_brackets_rate_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rebate_schedule_id: Mapped[int] = mapped_column(ForeignKey("rebate_schedules.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    lower: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    upper: Mapped[Decimal | None] = mapped_column(_AMOUNT, nullable=True)
    rate: Mapped[Decimal] = mapped_column(_RATE, nullable=False)


class PlatformRateSettingRecord(Base):
    """One platform rate setting. Rows are only added; the latest of a level and key is the one in force."""

    __tablename__ = "platform_rate_settings"
    __table_args__ = (
        CheckConstraint("level IN ('line', 'agency', 'campaign_type', 'system')", name="ck_platform_rate_settings_level"),
        CheckConstraint(
            "(level = 'line' AND campaign_line_id IS NOT NULL AND agency_id IS NULL AND campaign_type_id IS NULL)"
            " OR (level = 'agency' AND agency_id IS NOT NULL AND campaign_line_id IS NULL AND campaign_type_id IS NULL)"
            " OR (level = 'campaign_type' AND campaign_type_id IS NOT NULL AND campaign_line_id IS NULL"
            " AND agency_id IS NULL)"
            " OR (level = 'system' AND campaign_line_id IS NULL AND agency_id IS NULL AND campaign_type_id IS NULL)",
            name="ck_platform_rate_settings_level_key",
        ),
        CheckConstraint("level = 'system' OR created_by IS NOT NULL", name="ck_platform_rate_settings_author"),
        CheckConstraint("rate_per_thousand >= 0", name="ck_platform_rate_settings_rate_not_negative"),
        Index("ix_platform_rate_settings_level", "level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    campaign_line_id: Mapped[int | None] = mapped_column(ForeignKey("campaign_lines.id"), nullable=True)
    agency_id: Mapped[int | None] = mapped_column(ForeignKey("agencies.id"), nullable=True)
    campaign_type_id: Mapped[int | None] = mapped_column(ForeignKey("campaign_types.id"), nullable=True)
    rate_per_thousand: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class AppliedRateRecord(Base):
    """The rates and rebate frozen for one closed flight. Added once, never changed or deleted."""

    __tablename__ = "applied_rates"
    __table_args__ = (
        CheckConstraint("ladder_step IN (1, 2, 3, 4, 5, 6, 8)", name="ck_applied_rates_ladder_step"),
        CheckConstraint(
            "zero_reason IS NULL OR zero_reason IN ('no_schedule', 'no_schedule_for_year')",
            name="ck_applied_rates_zero_reason",
        ),
        CheckConstraint("platform_rate >= 0", name="ck_applied_rates_platform_rate_not_negative"),
        CheckConstraint(
            "(revenue_amount IS NULL) = (rebate_base_amount IS NULL)",
            name="ck_applied_rates_frozen_revenue_and_base_together",
        ),
        Index(
            "ix_applied_rates_counter", "counter_group_id", "counter_agency_id", "counter_channel_id", "counter_year"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    campaign_line_period_id: Mapped[int] = mapped_column(
        ForeignKey("campaign_line_periods.id"), nullable=False, unique=True
    )
    rebate_schedule_id: Mapped[int | None] = mapped_column(ForeignKey("rebate_schedules.id"), nullable=True)
    ladder_step: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agency_exception: Mapped[bool] = mapped_column(Boolean, nullable=False)
    zero_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    effective_rate: Mapped[Decimal] = mapped_column(_RATE, nullable=False)
    counter_group_id: Mapped[int] = mapped_column(ForeignKey("holding_groups.id"), nullable=False)
    counter_agency_id: Mapped[int | None] = mapped_column(ForeignKey("agencies.id"), nullable=True)
    counter_channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    counter_year: Mapped[int] = mapped_column(Integer, nullable=False)
    position_before: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    position_after: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    rebate_amount: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    platform_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    # Only for a target flight: the revenue its DSP reported and the gross its rebate was priced on, as of closing, so
    # that a later restatement does not move a closed month. Both null for a committed flight, whose sale is the contract.
    revenue_amount: Mapped[Decimal | None] = mapped_column(_AMOUNT, nullable=True)
    rebate_base_amount: Mapped[Decimal | None] = mapped_column(_AMOUNT, nullable=True)
    closed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    closed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)


class MonthClosingRecord(Base):
    """One closing run that froze at least one flight of a month. Added once, never changed or deleted.

    A month is closed when it holds one; it holds more when a flight registered in it after its closing is frozen by
    a later closing.
    """

    __tablename__ = "month_closings"
    __table_args__ = (
        CheckConstraint("period_month BETWEEN 1 AND 12", name="ck_month_closings_period_month"),
        Index("ix_month_closings_period", "period_year", "period_month"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    closed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    closed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # The last day the closing counted (D-1 of the day it ran).
    as_of: Mapped[date] = mapped_column(Date, nullable=False)


class MonthClosingBatchRecord(Base):
    """The latest succeeded ingestion batch of one DSP when a closing ran: the delivery its flights were frozen with."""

    __tablename__ = "month_closing_batches"

    month_closing_id: Mapped[int] = mapped_column(ForeignKey("month_closings.id"), primary_key=True)
    dsp_id: Mapped[int] = mapped_column(ForeignKey("dsps.id"), primary_key=True)
    ingestion_batch_id: Mapped[int] = mapped_column(ForeignKey("ingestion_batches.id"), nullable=False)


# Amounts frozen as the margin reports them, rounded to the cent; the window sums keep the precision of the delivery.
_ROUNDED = Numeric(18, 2)
_WINDOW_SUM = Numeric(18, 6)


class ClosedFlightSnapshotRecord(Base):
    """Every figure a closed flight reports and the delivery it was computed on. Added once, never changed or deleted.

    A closed flight is read only from here; the delivery stored afterwards only feeds the warning that it changed.
    """

    __tablename__ = "closed_flight_snapshots"
    __table_args__ = (
        CheckConstraint(
            "(volume_commitment = 'target') = (gross_revenue IS NOT NULL)",
            name="ck_closed_flight_snapshots_gross_with_target",
        ),
        CheckConstraint(
            "delivery_metric IN ('impressions', 'ots')", name="ck_closed_flight_snapshots_delivery_metric"
        ),
        CheckConstraint(
            "volume_commitment IN ('committed', 'target')", name="ck_closed_flight_snapshots_volume_commitment"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    applied_rate_id: Mapped[int] = mapped_column(ForeignKey("applied_rates.id"), nullable=False, unique=True)
    month_closing_id: Mapped[int] = mapped_column(ForeignKey("month_closings.id"), nullable=False, index=True)
    revenue: Mapped[Decimal] = mapped_column(_ROUNDED, nullable=False)
    contracted_revenue: Mapped[Decimal] = mapped_column(_ROUNDED, nullable=False)
    media_cost: Mapped[Decimal] = mapped_column(_ROUNDED, nullable=False)
    rebate: Mapped[Decimal] = mapped_column(_ROUNDED, nullable=False)
    platform_cost: Mapped[Decimal] = mapped_column(_ROUNDED, nullable=False)
    margin: Mapped[Decimal] = mapped_column(_ROUNDED, nullable=False)
    # Only a target flight has a gross: the check above ties it to the commitment.
    gross_revenue: Mapped[Decimal | None] = mapped_column(_ROUNDED, nullable=True)
    delivered_impressions: Mapped[int] = mapped_column(BigInteger, nullable=False)
    delivered: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    window_media_cost: Mapped[Decimal] = mapped_column(_WINDOW_SUM, nullable=False)
    window_reported_revenue: Mapped[Decimal] = mapped_column(_WINDOW_SUM, nullable=False)
    window_buyer_spend: Mapped[Decimal] = mapped_column(_WINDOW_SUM, nullable=False)
    window_data_cost: Mapped[Decimal] = mapped_column(_WINDOW_SUM, nullable=False)
    gross_differs_from_buyer_spend: Mapped[bool] = mapped_column(Boolean, nullable=False)
    data_cost_reported: Mapped[bool] = mapped_column(Boolean, nullable=False)
    delivery_metric: Mapped[str] = mapped_column(String, nullable=False)
    sale_cpm: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    contracted_impressions: Mapped[int] = mapped_column(BigInteger, nullable=False)
    volume_commitment: Mapped[str] = mapped_column(String, nullable=False)


class FlightBillingAdjustmentRecord(Base):
    """A manual adjustment of a committed flight's billing. Rows are only added; the latest of a flight is in force.

    The first three bases are recomputed from the delivery until the month is closed; `custom` carries its amount.
    """

    __tablename__ = "flight_billing_adjustments"
    __table_args__ = (
        CheckConstraint(
            "basis IN ('minimum', 'delivered', 'contracted', 'custom')", name="ck_flight_billing_adjustments_basis"
        ),
        CheckConstraint(
            "(basis = 'custom') = (amount IS NOT NULL)", name="ck_flight_billing_adjustments_amount_with_custom"
        ),
        CheckConstraint("amount IS NULL OR amount >= 0", name="ck_flight_billing_adjustments_amount_not_negative"),
        CheckConstraint("length(btrim(reason)) > 0", name="ck_flight_billing_adjustments_reason_not_blank"),
        Index("ix_flight_billing_adjustments_flight", "campaign_line_period_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    campaign_line_period_id: Mapped[int] = mapped_column(ForeignKey("campaign_line_periods.id"), nullable=False)
    basis: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(_ROUNDED, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class AppliedRateBracketRecord(Base):
    """The part of a frozen flight's revenue that fell in one bracket. Added once, never changed or deleted."""

    __tablename__ = "applied_rate_brackets"
    __table_args__ = (
        UniqueConstraint("applied_rate_id", "position", name="uq_applied_rate_brackets_rate_position"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    applied_rate_id: Mapped[int] = mapped_column(ForeignKey("applied_rates.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    lower: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    upper: Mapped[Decimal | None] = mapped_column(_AMOUNT, nullable=True)
    rate: Mapped[Decimal] = mapped_column(_RATE, nullable=False)
    amount: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    rebate: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
