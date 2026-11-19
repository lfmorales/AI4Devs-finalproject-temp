"""Master data tables: agencies, advertisers, DSPs, channels, formats, campaign types, sectors, sales reps."""

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.base import Base


class HoldingGroupRecord(Base):
    __tablename__ = "holding_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)


class AgencyRecord(Base):
    __tablename__ = "agencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    holding_group_id: Mapped[int] = mapped_column(ForeignKey("holding_groups.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)


class AdvertiserRecord(Base):
    __tablename__ = "advertisers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)


class DSPRecord(Base):
    __tablename__ = "dsps"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ChannelRecord(Base):
    __tablename__ = "channels"
    __table_args__ = (
        CheckConstraint("delivery_metric IN ('impressions', 'ots')", name="ck_channels_delivery_metric"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # The unit of the contracted and delivered volume of the channel's lines: impressions, or OTS for DOOH.
    delivery_metric: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'impressions'"))


class FormatRecord(Base):
    __tablename__ = "formats"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)


class CampaignTypeRecord(Base):
    __tablename__ = "campaign_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)


class SectorRecord(Base):
    __tablename__ = "sectors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)


class SalesRepRecord(Base):
    __tablename__ = "sales_reps"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
