"""Create synthetic demonstration data to work the exception queue. Nothing here is real.

It registers two campaigns with neutral names, with dates relative to today in Madrid:

- DEMO-EXC-CAMPANA has one line with no mapping, started twenty days ago: it is the line to link an exception to,
  and linking answers that the history before the normal window has to be loaded.
- DEMO-EXC-AUSENCIA fills the whole previous month with one line that is already mapped and validated and has no
  delivery at all: its finished flight carries the missing-delivery exception.

It adds five DSP catalogue lines named "DEMO Catalogo Linea 1" to "5" (two with accents, to try the search without
accents) and, through the exception repository, four unmatched-delivery exceptions on the pairs of the first four
of them, with the delivery of the last five days retained by day: three stay open and one is resolved with a note.
The fifth pair is the mapped line of the absence campaign. Every external identifier has nine digits and starts with
99, so none can be an identifier of the real Adform (seven or eight digits).

Everything goes through the real services and repositories: the registration service, the catalogue and mapping
repositories, the exception repository and the exception service. The campaigns and masters are the ones of
seed_margin_demo, whose loader and registration are reused. The exceptions are resolved by the development user,
who must exist already (seed_dev_data creates it): this command never creates a user or a role.

Running it again changes nothing the same day: what exists is kept (a resolved exception stays resolved) and the
retained delivery is written again; a later day only adds its new days.

The output is counts only: no name, no identifier, no email.

Exit codes: 0 done; 1 the database failed; 2 invalid arguments; 3 DATABASE_URL is missing; 4 there is no
development user (run seed_dev_data first).

Run: python -m scripts.seed_exceptions_demo
"""

import os
import sys
from calendar import monthrange
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.services.ingestion_exception_service import IngestionExceptionService
from app.domain.entities.ingestion_exception import ExceptionStatus
from app.domain.services.local_calendar import local_today, utc_now
from app.domain.value_objects.catalog import CatalogLineObservation
from app.domain.value_objects.delivery import DeliveryDateRange, ExternalLineKey, RetainedDelivery
from app.infrastructure.persistence.database import build_engine, build_session_factory
from app.infrastructure.persistence.models.campaign import CampaignLinePeriodRecord, CampaignLineRecord, CampaignRecord
from app.infrastructure.persistence.models.delivery import IngestionExceptionDeliveryRecord, IngestionExceptionRecord
from app.infrastructure.persistence.models.dsp_catalog import DspCatalogLineRecord
from app.infrastructure.persistence.models.masters import DSPRecord
from app.infrastructure.persistence.repositories.sqlalchemy_dsp_catalog_repository import SqlAlchemyDspCatalogRepository
from app.infrastructure.persistence.repositories.sqlalchemy_dsp_mapping_repository import SqlAlchemyDspMappingRepository
from app.infrastructure.persistence.repositories.sqlalchemy_exception_queue_repository import (
    SqlAlchemyExceptionQueueRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_ingestion_exception_repository import (
    SqlAlchemyIngestionExceptionRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from scripts.load_masters import _load
from scripts.seed_margin_demo import (
    MADRID,
    DemoCampaign,
    _batch,
    _id_of,
    _InvalidArguments,
    _MASTERS,
    _Parser,
    _register_missing,
)

EXIT_OK, EXIT_FAILED, EXIT_INVALID_ARGUMENTS, EXIT_NOT_CONFIGURED, EXIT_NO_DEVELOPMENT_USER = 0, 1, 2, 3, 4

CAMPAIGN_NAME = "DEMO-EXC-CAMPANA"
ABSENCE_NAME = "DEMO-EXC-AUSENCIA"
BATCH_SOURCE = "demo-exceptions"
RESOLUTION_NOTE = "Demonstration: resolved without linking"
RETAINED_DAYS = 5


@dataclass(frozen=True)
class CatalogDemoLine:
    external_campaign_id: str
    external_line_item_id: str
    campaign_name: str
    line_item_name: str


# Identifiers: nine digits starting with 99. The real Adform ones have seven or eight digits.
CATALOG_LINES: tuple[CatalogDemoLine, ...] = (
    CatalogDemoLine("991000001", "992000001", "DEMO Catálogo Campaña 1", "DEMO Catálogo Línea 1"),
    CatalogDemoLine("991000002", "992000002", "DEMO Catálogo Campaña 2", "DEMO Catálogo Línea 2"),
    CatalogDemoLine("991000003", "992000003", "DEMO Catalogo Campana 3", "DEMO Catalogo Linea 3"),
    CatalogDemoLine("991000004", "992000004", "DEMO Catalogo Campana 4", "DEMO Catalogo Linea 4"),
    CatalogDemoLine("991000005", "992000005", "DEMO Catalogo Campana 5", "DEMO Catalogo Linea 5"),
)
OPEN_UNMATCHED = CATALOG_LINES[0:3]
RESOLVED_UNMATCHED = CATALOG_LINES[3]
MAPPED_TO_ABSENCE = CATALOG_LINES[4]


def _key(line: CatalogDemoLine) -> ExternalLineKey:
    return ExternalLineKey(line.external_campaign_id, line.external_line_item_id)


def demo_campaigns(today: date) -> list[DemoCampaign]:
    """The two campaigns, dated from `today`; the absence one fills the previous month."""
    previous_last = today.replace(day=1) - timedelta(days=1)
    previous_first = previous_last.replace(day=1)
    assert previous_last.day == monthrange(previous_last.year, previous_last.month)[1]
    return [
        DemoCampaign(CAMPAIGN_NAME, "DEMO-EXC-PO-CAMPANA", today - timedelta(days=20), today + timedelta(days=20),
                     1_000_000, "5.00", Decimal("0")),
        DemoCampaign(ABSENCE_NAME, "DEMO-EXC-PO-AUSENCIA", previous_first, previous_last, 1_000_000, "5.00", Decimal("0")),
    ]


def main(
    argv: Sequence[str] | None = None,
    *,
    out: Callable[[str], None] = print,
    session_factory: Callable[[], Session] | None = None,
    today: date | None = None,
    clock: Callable[[], datetime] = utc_now,
    developer_email: str | None = None,
) -> int:
    try:
        _Parser(prog="seed_exceptions_demo", description="Create synthetic demonstration data for the exception queue.").parse_args(argv)
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

    email = developer_email if developer_email is not None else os.environ.get("SEED_USER_EMAIL")
    day = today if today is not None else local_today(MADRID, clock)
    session = session_factory()
    try:
        developer = SqlAlchemyUserRepository(session).get_by_email(email) if email else None
        if developer is None:
            out("status: no development user: run seed_dev_data first")
            return EXIT_NO_DEVELOPMENT_USER
        counts = seed(session, day, started_at=clock().replace(tzinfo=None), resolver_id=developer.id)
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


def seed(session: Session, today: date, started_at: datetime, resolver_id: int) -> dict[str, int]:
    """Create what is missing, write the retained delivery again, and return the counts to print."""
    masters_created = sum(_load(session, section, items) for section, items in _MASTERS.items())  # type: ignore[arg-type]
    session.commit()
    campaigns = demo_campaigns(today)
    created = _register_missing(session, campaigns)
    dsp_id = _id_of(session, DSPRecord, "DEMO DSP")
    yesterday = today - timedelta(days=1)
    window = DeliveryDateRange(today - timedelta(days=RETAINED_DAYS), yesterday)
    batch_id = _batch(session, window, started_at, BATCH_SOURCE)

    _write_catalogue(session, dsp_id, today)
    mappings_created = _map_absence_line(session, dsp_id, started_at)
    exceptions_before = _count(session, IngestionExceptionRecord.id)
    _write_unmatched(session, dsp_id, batch_id, window, started_at, resolver_id)
    missing_created = _record_missing_delivery(session, batch_id)
    return {
        "masters created": masters_created,
        "campaigns created": created,
        "campaigns existing": len(campaigns) - created,
        "catalogue lines": _count(session, DspCatalogLineRecord.id),
        "mappings created": mappings_created,
        "exceptions created": _count(session, IngestionExceptionRecord.id) - exceptions_before,
        "exceptions open": _count(session, IngestionExceptionRecord.id, IngestionExceptionRecord.status == "open"),
        "exceptions resolved": _count(session, IngestionExceptionRecord.id, IngestionExceptionRecord.status == "resolved"),
        "missing deliveries created": int(missing_created),
        "retained days": _count(session, IngestionExceptionDeliveryRecord.id),
    }


def _count(session: Session, column, *conditions) -> int:  # type: ignore[no-untyped-def]
    return session.scalar(select(func.count(column)).where(*conditions)) or 0


def _line_id(session: Session, campaign_name: str) -> int:
    return session.scalars(
        select(CampaignLineRecord.id).join(CampaignRecord, CampaignRecord.id == CampaignLineRecord.campaign_id)
        .where(CampaignRecord.name == campaign_name)
    ).one()


def _write_catalogue(session: Session, dsp_id: int, today: date) -> None:
    """The five catalogue lines, seen over the retained window; the first four delivered impressions yesterday."""
    first_seen, last_seen = today - timedelta(days=RETAINED_DAYS), today - timedelta(days=1)
    SqlAlchemyDspCatalogRepository(session).upsert_all(dsp_id, [
        CatalogLineObservation(
            key=_key(line), campaign_name=line.campaign_name, line_item_name=line.line_item_name,
            line_start_date=None, line_end_date=None, first_seen_date=first_seen, last_seen_date=last_seen,
            last_impressions_date=None if line is MAPPED_TO_ABSENCE else last_seen,
        )
        for line in CATALOG_LINES
    ])


def _map_absence_line(session: Session, dsp_id: int, started_at: datetime) -> int:
    """Map and validate the pair of the absence line, once; return how many mappings were created."""
    mappings = SqlAlchemyDspMappingRepository(session)
    key = _key(MAPPED_TO_ABSENCE)
    if mappings.pair_exists(dsp_id, key):
        return 0
    mappings.add(_line_id(session, ABSENCE_NAME), dsp_id, key, started_at)
    return 1


def _invented_day(line: CatalogDemoLine, day: date) -> RetainedDelivery:
    """Invented retained delivery for one day, with a small ripple by day of the month."""
    impressions = 40_000 + (day.day % 5) * 1_000
    return RetainedDelivery(
        key=_key(line), delivery_date=day, impressions=impressions, clicks=impressions // 500,
        media_cost=(Decimal(impressions) / Decimal(1000) * Decimal("1.50")).quantize(Decimal("0.000001")),
        measurable_impressions=impressions * 9 // 10, viewable_impressions=impressions * 7 // 10,
    )


def _write_unmatched(
    session: Session, dsp_id: int, batch_id: int, window: DeliveryDateRange, started_at: datetime, resolver_id: int
) -> None:
    exceptions = SqlAlchemyIngestionExceptionRepository(session)
    exceptions.delete_retained_range(dsp_id, window)
    ids = {}
    for line in (*OPEN_UNMATCHED, RESOLVED_UNMATCHED):
        ids[line] = exceptions.get_or_create_unmatched(dsp_id, _key(line), batch_id)
        exceptions.add_retained(ids[line], [_invented_day(line, day) for day in window.days()])
    exceptions.refresh_unmatched_date_spans(dsp_id)

    queue = SqlAlchemyExceptionQueueRepository(session)
    resolved = queue.get_summary(ids[RESOLVED_UNMATCHED])
    if resolved is not None and resolved.status is ExceptionStatus.OPEN:
        IngestionExceptionService(queue, lambda: started_at).resolve(ids[RESOLVED_UNMATCHED], resolver_id, RESOLUTION_NOTE)


def _record_missing_delivery(session: Session, batch_id: int) -> bool:
    """The absence of the finished flight of the mapped line; True if it was new."""
    line_id = _line_id(session, ABSENCE_NAME)
    period_id = session.scalars(
        select(CampaignLinePeriodRecord.campaign_period_id).where(CampaignLinePeriodRecord.campaign_line_id == line_id)
        .order_by(CampaignLinePeriodRecord.flight_start)
    ).first()
    assert period_id is not None
    return SqlAlchemyIngestionExceptionRepository(session).record_missing_delivery(line_id, period_id, batch_id)


if __name__ == "__main__":
    sys.exit(main())
