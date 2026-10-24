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


def insert_campaign_line(session: Session, campaign_name: str = "Delivery fixture campaign") -> int:
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
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )
    session.add(campaign)
    session.flush()
    period = CampaignPeriodRecord(
        campaign_id=campaign.id,
        period_year=2026,
        period_month=8,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
    )
    session.add(period)
    session.flush()
    line = CampaignLineRecord(
        campaign_period_id=period.id,
        dsp_id=seeded_dsp_id(session),
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
