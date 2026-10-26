"""Margin tables: rebate schedules and brackets, platform rate settings, and the rates frozen at closing."""

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
    closed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    closed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)


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
