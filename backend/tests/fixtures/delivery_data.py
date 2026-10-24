"""Builders for persisted campaign lines and ingestion batches that delivery rows can reference.

These create their own master rows instead of calling seed_master_data: that helper restarts
identity sequences, which collides with rows other infrastructure tests commit for real.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.campaign import (
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
)
from app.infrastructure.persistence.models.delivery import IngestionBatchRecord
from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord
from app.infrastructure.persistence.models.masters import (
    AdvertiserRecord,
    AgencyRecord,
    CampaignTypeRecord,
    ChannelRecord,
    DSPRecord,
    FormatRecord,
    HoldingGroupRecord,
    SalesRepRecord,
    SectorRecord,
)

CONTRACTED_IMPRESSIONS = 1_000_000
_DSP_NAME = "Delivery fixture DSP"


def seeded_dsp_id(session: Session) -> int:
    """Return the id of the fixture DSP, creating it on first use within the session."""
    dsp = session.scalars(select(DSPRecord).where(DSPRecord.name == _DSP_NAME)).first()
    if dsp is None:
        dsp = DSPRecord(name=_DSP_NAME, is_active=True)
        session.add(dsp)
        session.flush()
    return dsp.id


def insert_campaign_line(
    session: Session,
    campaign_name: str = "Delivery fixture campaign",
    start_date: date = date(2026, 8, 1),
    end_date: date = date(2026, 8, 31),
    status: str = "active",
    dsp_id: int | None = None,
) -> int:
    """Persist a campaign with one period and one line, and return the line id."""
    holding_group = HoldingGroupRecord(name=f"{campaign_name} group")
    advertiser = AdvertiserRecord(name=f"{campaign_name} advertiser")
    campaign_type = CampaignTypeRecord(name=f"{campaign_name} type")
    sector = SectorRecord(name=f"{campaign_name} sector")
    sales_rep = SalesRepRecord(name=f"{campaign_name} rep")
    channel = ChannelRecord(name=f"{campaign_name} channel")
    line_format = FormatRecord(name=f"{campaign_name} format")
    session.add_all([holding_group, advertiser, campaign_type, sector, sales_rep, channel, line_format])
    session.flush()
    agency = AgencyRecord(holding_group_id=holding_group.id, name=f"{campaign_name} agency")
    session.add(agency)
    session.flush()

    campaign = CampaignRecord(
        name=campaign_name,
        display_name=campaign_name,
        agency_id=agency.id,
        advertiser_id=advertiser.id,
        campaign_type_id=campaign_type.id,
        sector_id=sector.id,
        sales_rep_id=sales_rep.id,
        start_date=start_date,
        end_date=end_date,
        status=status,
    )
    session.add(campaign)
    session.flush()
    period = CampaignPeriodRecord(
        campaign_id=campaign.id,
        period_year=2026,
        period_month=8,
        period_start=start_date,
        period_end=end_date,
    )
    session.add(period)
    session.flush()
    line = CampaignLineRecord(
        campaign_period_id=period.id,
        dsp_id=dsp_id if dsp_id is not None else seeded_dsp_id(session),
        channel_id=channel.id,
        format_id=line_format.id,
        scope="national",
        market_description="Nacional",
        contracted_impressions=CONTRACTED_IMPRESSIONS,
        sale_cpm=Decimal("5.00"),
    )
    session.add(line)
    session.flush()
    return line.id


def insert_ingestion_batch(session: Session, route: str = "api") -> int:
    """Persist a finished ingestion batch for the fixture DSP and return its id."""
    batch = IngestionBatchRecord(
        dsp_id=seeded_dsp_id(session),
        route=route,
        source_file=None,
        started_at=datetime(2026, 8, 4, 2, 0),
        finished_at=datetime(2026, 8, 4, 2, 5),
        status="succeeded",
        row_count=0,
    )
    session.add(batch)
    session.flush()
    return batch.id


def insert_other_dsp(session: Session, name: str = "Another fixture DSP") -> int:
    dsp = DSPRecord(name=name, is_active=True)
    session.add(dsp)
    session.flush()
    return dsp.id


def insert_mapping(
    session: Session,
    campaign_line_id: int,
    dsp_id: int,
    external_campaign_id: str = "1001",
    external_line_item_id: str = "2001",
    validated_at: datetime | None = datetime(2026, 8, 1, 9, 0),
) -> None:
    session.add(DSPMappingRecord(
        campaign_line_id=campaign_line_id,
        dsp_id=dsp_id,
        external_campaign_id=external_campaign_id,
        external_line_item_id=external_line_item_id,
        validated_at=validated_at,
    ))
    session.flush()


def campaign_id_of(session: Session, campaign_line_id: int) -> int:
    return session.scalars(
        select(CampaignRecord.id)
        .join(CampaignPeriodRecord, CampaignPeriodRecord.campaign_id == CampaignRecord.id)
        .join(CampaignLineRecord, CampaignLineRecord.campaign_period_id == CampaignPeriodRecord.id)
        .where(CampaignLineRecord.id == campaign_line_id)
    ).one()


def insert_user(session: Session, email: str = "resolver@example.com") -> int:
    from app.infrastructure.persistence.models.identity import UserRecord

    user = UserRecord(email=email, full_name="Resolver", is_active=True)
    session.add(user)
    session.flush()
    return user.id


def insert_delivery(session: Session, campaign_line_id: int, delivery_day: date, impressions: int, batch_id: int) -> None:
    from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord

    session.add(DailyDeliveryRecord(
        campaign_line_id=campaign_line_id, ingestion_batch_id=batch_id, delivery_date=delivery_day,
        impressions=impressions, clicks=0, media_cost=Decimal("0"), measurable_impressions=0, viewable_impressions=0,
    ))
    session.flush()
