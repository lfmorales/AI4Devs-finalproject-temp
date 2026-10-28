"""Create synthetic demonstration data to see the states of the margin. Nothing here is real.

It registers four campaigns with neutral names, one line each, with dates relative to today in Madrid:

- DEMO-MARGEN-CERRADO fills the whole previous month: it has ended and is pending close until that month is closed.
- DEMO-MARGEN-CURSO starts ten days ago and ends next month: it is running, with an invented media cost of 1.60
  per thousand against a sale CPM of 6.00, so its margin is positive.
- DEMO-MARGEN-NEGATIVO has the same window and volume and the same CPM, but an invented media cost of 9.00 per
  thousand: it is running and shows "Margen negativo".
- DEMO-MARGEN-SIN-PRECIO is the same window with a sale CPM of 0.00 and a positive volume: running, "Sin venta".

It also invents daily deliveries for each line up to yesterday and a flat example rebate schedule for a
demonstration holding group. The campaigns go through the registration service, the deliveries through the delivery
repository, the master data through the master loader and the schedule through the schedule service: no row is
inserted by hand except the demonstration masters' names, which the loader writes.

Running it again changes nothing the same day: what exists is kept, the deliveries are written again with the current
invented costs (so a database seeded earlier gets the new ones), and a later day only adds its new days. It never creates a user, a role, a platform rate or a frozen rate.

The output is counts only: no name, no id, no date.

Exit codes: 0 done; 1 the database failed; 2 invalid arguments; 3 DATABASE_URL is missing.

Run: python -m scripts.seed_margin_demo
"""

import argparse
import asyncio
import os
import sys
from calendar import monthrange
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.services.campaign_registration_service import CampaignRegistrationService
from app.application.services.margin_masters_service import MarginMastersService
from app.domain.entities.ingestion_batch import BatchStatus, IngestionRoute
from app.domain.services.local_calendar import local_today, utc_now
from app.domain.value_objects.delivery import DailyDelivery, DeliveryDateRange
from app.domain.value_objects.rebate import Bracket, NewRebateSchedule
from app.infrastructure.persistence.database import build_engine, build_session_factory
from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignRecord,
)
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord, IngestionBatchRecord
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
from app.infrastructure.persistence.repositories import (
    CampaignRepositoryImpl,
    MasterRepositoryImpl,
    PurchaseOrderRepositoryImpl,
)
from app.infrastructure.persistence.repositories.sqlalchemy_delivery_repository import (
    SqlAlchemyDeliveryRepository,
    SqlAlchemyIngestionBatchRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_margin_repositories import (
    SqlAlchemyMarginMastersTransaction,
    SqlAlchemyRebateScheduleRepository,
)
from scripts.load_masters import _load

EXIT_OK, EXIT_FAILED, EXIT_INVALID_ARGUMENTS, EXIT_NOT_CONFIGURED = 0, 1, 2, 3

CLOSED_NAME = "DEMO-MARGEN-CERRADO"
RUNNING_NAME = "DEMO-MARGEN-CURSO"
NEGATIVE_NAME = "DEMO-MARGEN-NEGATIVO"
NO_PRICE_NAME = "DEMO-MARGEN-SIN-PRECIO"

MADRID = "Europe/Madrid"
BATCH_SOURCE = "demo-margin"
EXAMPLE_REBATE_RATE = Decimal("0.10")

# The demonstration masters, loaded like any other master data. All of them are named DEMO.
_MASTERS: dict[str, list[dict[str, object]]] = {
    "holding_groups": [{"name": "DEMO Holding"}],
    "agencies": [{"name": "DEMO Agency", "holding_group": "DEMO Holding"}],
    "advertisers": [{"name": "DEMO Advertiser"}],
    "dsps": [{"name": "DEMO DSP", "is_active": True}],
    "channels": [{"name": "DEMO Channel"}],
    "formats": [{"name": "DEMO Format"}],
    "campaign_types": [{"name": "DEMO Campaign Type"}],
    "sectors": [{"name": "DEMO Sector"}],
    "sales_reps": [{"name": "DEMO Sales Rep"}],
}


class _InvalidArguments(Exception):
    """Carries no detail: the output never echoes what was typed."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # type: ignore[no-untyped-def]
        raise _InvalidArguments()


@dataclass(frozen=True)
class DemoCampaign:
    name: str
    order_reference: str
    start: date
    end: date
    volume: int
    sale_cpm: str
    # Euros per thousand delivered impressions that the invented media cost is worth.
    cost_cpm: Decimal


def _last_day_of_next_month(today: date) -> date:
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return date(year, month, monthrange(year, month)[1])


def demo_campaigns(today: date) -> list[DemoCampaign]:
    """The four campaigns, dated from `today`. The running ones start ten days ago and end next month."""
    previous_last = today.replace(day=1) - timedelta(days=1)
    previous_first = previous_last.replace(day=1)
    running_start, running_end = today - timedelta(days=10), _last_day_of_next_month(today)
    return [
        DemoCampaign(CLOSED_NAME, "DEMO-MARGEN-PO-CERRADO", previous_first, previous_last, 3_000_000, "5.00", Decimal("2.00")),
        # A media cost per thousand well below the sale CPM: a positive margin of around 45 % of the revenue.
        DemoCampaign(RUNNING_NAME, "DEMO-MARGEN-PO-CURSO", running_start, running_end, 2_400_000, "6.00", Decimal("1.60")),
        # A media cost per thousand above the sale CPM: the delivered cost is above the revenue it accrues.
        DemoCampaign(NEGATIVE_NAME, "DEMO-MARGEN-PO-NEGATIVO", running_start, running_end, 2_400_000, "6.00", Decimal("9.00")),
        DemoCampaign(NO_PRICE_NAME, "DEMO-MARGEN-PO-SIN-PRECIO", running_start, running_end, 1_000_000, "0.00", Decimal("3.00")),
    ]


def main(
    argv: Sequence[str] | None = None,
    *,
    out: Callable[[str], None] = print,
    session_factory: Callable[[], Session] | None = None,
    today: date | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> int:
    try:
        _Parser(prog="seed_margin_demo", description="Create synthetic demonstration data for the margin.").parse_args(argv)
    except _InvalidArguments:
        out("status: invalid arguments")
        return EXIT_INVALID_ARGUMENTS

    engine = None
    if session_factory is None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            out("status: not configured")
            return EXIT_NOT_CONFIGURED
        engine = build_engine(database_url)
        session_factory = build_session_factory(engine)

    day = today if today is not None else local_today(MADRID, clock)
    session = session_factory()
    try:
        counts = seed(session, day, started_at=clock().replace(tzinfo=None))
        session.commit()
    except Exception:
        session.rollback()
        out("status: failed")
        return EXIT_FAILED
    finally:
        session.close()
        if engine is not None:
            engine.dispose()

    for label, value in counts.items():
        out(f"{label}: {value}")
    return EXIT_OK


def seed(session: Session, today: date, started_at: datetime) -> dict[str, int]:
    """Create what is missing, write the deliveries again, and return the counts to print."""
    masters_created = sum(_load(session, section, items) for section, items in _MASTERS.items())  # type: ignore[arg-type]
    session.commit()
    campaigns = demo_campaigns(today)
    created = _register_missing(session, campaigns)
    schedules_created = _ensure_rebate_schedule(session, today)
    _write_deliveries(session, campaigns, today - timedelta(days=1), started_at)
    return {
        "masters created": masters_created,
        "campaigns created": created,
        "campaigns existing": len(campaigns) - created,
        "rebate schedules created": schedules_created,
        **_stored_counts(session),
    }


def _id_of(session: Session, model: type, name: str) -> int:
    return session.scalars(select(model.id).where(model.name == name)).one()  # type: ignore[attr-defined]


def _register_missing(session: Session, campaigns: list[DemoCampaign]) -> int:
    """Register, through the registration service, the campaigns that do not exist yet; return how many."""
    service = CampaignRegistrationService(
        campaign_repo=CampaignRepositoryImpl(session),
        purchase_order_repo=PurchaseOrderRepositoryImpl(session),
        master_repo=MasterRepositoryImpl(session),
    )
    ids = {
        "agency_id": _id_of(session, AgencyRecord, "DEMO Agency"),
        "advertiser_id": _id_of(session, AdvertiserRecord, "DEMO Advertiser"),
        "campaign_type_id": _id_of(session, CampaignTypeRecord, "DEMO Campaign Type"),
        "sector_id": _id_of(session, SectorRecord, "DEMO Sector"),
        "sales_rep_id": _id_of(session, SalesRepRecord, "DEMO Sales Rep"),
    }
    line_ids = {
        "dsp_id": _id_of(session, DSPRecord, "DEMO DSP"),
        "channel_id": _id_of(session, ChannelRecord, "DEMO Channel"),
        "format_id": _id_of(session, FormatRecord, "DEMO Format"),
    }
    created = 0
    for campaign in campaigns:
        if session.scalar(select(CampaignRecord.id).where(CampaignRecord.name == campaign.name)) is not None:
            continue
        asyncio.run(service.register_campaign(
            name=campaign.name,
            display_name=campaign.name,
            start_date=campaign.start,
            end_date=campaign.end,
            order_reference=campaign.order_reference,
            order_received_on=campaign.start,
            lines_data=[{
                **line_ids,
                "scope": "national",
                "market_description": "DEMO",
                "contracted_impressions": campaign.volume,
                "sale_cpm": campaign.sale_cpm,
            }],
            **ids,
        ))
        created += 1
    return created


def _ensure_rebate_schedule(session: Session, today: date) -> int:
    """A flat example rebate for the demonstration group, once; return how many were created."""
    group_id = _id_of(session, HoldingGroupRecord, "DEMO Holding")
    if any(schedule.group_id == group_id for schedule in SqlAlchemyRebateScheduleRepository(session).list_schedules()):
        return 0
    previous_year = (today.replace(day=1) - timedelta(days=1)).year
    MarginMastersService(SqlAlchemyMarginMastersTransaction(session)).create_schedule(NewRebateSchedule(
        holding_group_id=group_id, agency_id=None, channel_id=None, scope=None,
        valid_from=date(previous_year, 1, 1), valid_to=None,
        brackets=(Bracket(Decimal(0), None, EXAMPLE_REBATE_RATE),),
    ))
    return 1


def _batch(session: Session, window: DeliveryDateRange, started_at: datetime) -> int:
    existing = session.scalar(select(IngestionBatchRecord.id).where(IngestionBatchRecord.source_file == BATCH_SOURCE))
    if existing is not None:
        return existing
    batches = SqlAlchemyIngestionBatchRepository(session)
    batch_id = batches.start(_id_of(session, DSPRecord, "DEMO DSP"), IngestionRoute.UPLOAD, BATCH_SOURCE, started_at, window)
    batches.finish(batch_id, BatchStatus.SUCCEEDED, started_at, 0, 0, 0)
    return batch_id


def _invented_day(campaign: DemoCampaign, day: date) -> DailyDelivery:
    """Invented delivery for one day: roughly the contracted pace, with a small ripple by day of the month."""
    total_days = (campaign.end - campaign.start).days + 1
    impressions = campaign.volume // total_days + (day.day % 5) * 1000
    cost = (Decimal(impressions) / Decimal(1000) * campaign.cost_cpm).quantize(Decimal("0.000001"))
    return DailyDelivery(
        campaign_line_id=0, ingestion_batch_id=0, delivery_date=day, impressions=impressions,
        clicks=impressions // 500, media_cost=cost, measurable_impressions=impressions * 9 // 10,
        viewable_impressions=impressions * 7 // 10, banner_size=None, screen=None, line_format=None,
    )


def _write_deliveries(session: Session, campaigns: list[DemoCampaign], as_of: date, started_at: datetime) -> None:
    """Write the invented deliveries of each line from its start to `as_of`, replacing what was there."""
    batch_id = _batch(session, DeliveryDateRange(min(c.start for c in campaigns), as_of), started_at)
    deliveries = SqlAlchemyDeliveryRepository(session)
    for campaign in campaigns:
        line_id = session.scalars(
            select(CampaignLineRecord.id).join(CampaignRecord, CampaignRecord.id == CampaignLineRecord.campaign_id)
            .where(CampaignRecord.name == campaign.name)
        ).one()
        last_day = min(as_of, campaign.end)
        window = DeliveryDateRange(campaign.start, last_day)
        deliveries.delete_range([line_id], window)
        deliveries.add_all(
            replace(_invented_day(campaign, day), campaign_line_id=line_id, ingestion_batch_id=batch_id)
            for day in window.days()
        )


def _stored_counts(session: Session) -> dict[str, int]:
    demo = CampaignRecord.name.like("DEMO-MARGEN-%")
    lines = select(CampaignLineRecord.id).join(CampaignRecord, CampaignRecord.id == CampaignLineRecord.campaign_id).where(demo)
    return {
        "lines": session.scalar(select(func.count()).select_from(lines.subquery())) or 0,
        "flights": session.scalar(
            select(func.count()).select_from(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.campaign_line_id.in_(lines))
        ) or 0,
        "deliveries stored": session.scalar(
            select(func.count()).select_from(DailyDeliveryRecord).where(DailyDeliveryRecord.campaign_line_id.in_(lines))
        ) or 0,
    }


if __name__ == "__main__":
    sys.exit(main())
