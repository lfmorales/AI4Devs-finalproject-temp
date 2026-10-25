"""The nightly ingestion: one command for the host scheduler, using the same service as every other route.

Calculates the window for today (in the configured time zone, or --date), ingests the lines with a validated
Adform mapping with one request, records the batch, and then detects absence with that batch's id. A
PostgreSQL advisory lock stops two runs overlapping.

Exit codes: 0 the batch succeeded; 1 it failed; 2 another run holds the lock; 3 configuration is missing.

It prints states and counts only: never an identifier, a name, an amount, a token or the text of a DSP error;
a failure is summarised by the name of its error class.

A custom range, --from YYYY-MM-DD --to YYYY-MM-DD, replaces the rolling window with one request for the whole
range (at most 31 days, ending no later than yesterday in the configured zone). It uses the same service and the
same idempotent replacement, records the range on the batch and skips the absence detection. It cannot be combined
with --date, and invalid arguments exit with 3 like every other configuration problem.

Run: python -m scripts.run_ingestion [--date YYYY-MM-DD | --from YYYY-MM-DD --to YYYY-MM-DD]
Example crontab line (not installed): see design.md.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta

import httpx
from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.application.services.delivery_ingestion_service import DeliveryIngestionService
from app.domain.entities.ingestion_batch import IngestionRoute
from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.services.local_calendar import local_today, utc_now
from app.domain.value_objects.delivery import DeliveryDateRange
from app.infrastructure.dsp.adform_delivery_client import AdformDeliveryClient
from app.infrastructure.persistence.database import build_engine, build_session_factory
from app.infrastructure.persistence.models.delivery import IngestionExceptionRecord
from app.infrastructure.persistence.models.masters import DSPRecord
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

EXIT_SUCCEEDED, EXIT_FAILED, EXIT_ALREADY_RUNNING, EXIT_NOT_CONFIGURED = 0, 1, 2, 3
# Arbitrary but fixed: every run of this command asks for the same session-level advisory lock.
NIGHTLY_INGESTION_LOCK_KEY = 0x41444F50
_DSP_NAME = "Adform"
MAX_RANGE_DAYS = 31


class _NotConfigured(Exception):
    """Something the run needs is missing or malformed. Carries no detail: the output never echoes values."""


class _Settings(BaseSettings):
    """Only what this command reads, so it does not need the Cognito settings of the API."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    database_url: str
    app_timezone: str = "Europe/Madrid"
    adform_client_id: str | None = None
    adform_client_secret: SecretStr | None = None


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # type: ignore[no-untyped-def]
        # Argparse would exit with 2, which this command reserves for "another run holds the lock".
        raise _NotConfigured()


def main(
    argv: Sequence[str] | None = None,
    *,
    out: Callable[[str], None] = print,
    engine: Engine | None = None,
    session_factory: Callable[[], Session] | None = None,
    client: DspDeliveryClient | None = None,
    now: Callable[[], datetime] = utc_now,
) -> int:
    try:
        arguments = _parse(argv)
        settings = _settings()
        # Evaluated even with --date, so a mistyped time zone is caught on every run.
        zone_today = local_today(settings.app_timezone, now)
        today = arguments.date or zone_today
        custom_window = _custom_window(arguments, zone_today)
        dsp_client = client or _adform_client(settings)
    except (_NotConfigured, ValidationError, ValueError):
        out("status: not configured")
        return EXIT_NOT_CONFIGURED

    own_engine = engine is None
    engine = engine or build_engine(settings.database_url)
    try:
        return _run_locked(
            engine, session_factory or build_session_factory(engine), dsp_client, today, out, custom_window
        )
    finally:
        if own_engine:
            engine.dispose()


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _Parser(prog="run_ingestion", description="Run the nightly Adform ingestion.")
    parser.add_argument("--date", type=_iso_date, help="use this date instead of today, to repeat a window")
    parser.add_argument("--from", dest="range_start", type=_iso_date, help="first day of a custom range")
    parser.add_argument("--to", dest="range_end", type=_iso_date, help="last day of a custom range")
    return parser.parse_args(argv)


def _custom_window(arguments: argparse.Namespace, zone_today: date) -> DeliveryDateRange | None:
    """The custom range the arguments ask for, None when they ask for the rolling window.

    Both ends or neither, never with --date, at most 31 days, and ending no later than yesterday in the zone: a
    day that is not over has no final figures to replace.
    """
    start, end = arguments.range_start, arguments.range_end
    if start is None and end is None:
        return None
    if start is None or end is None or arguments.date is not None or start > end:
        raise _NotConfigured()
    if (end - start).days + 1 > MAX_RANGE_DAYS or end > zone_today - timedelta(days=1):
        raise _NotConfigured()
    return DeliveryDateRange(start, end)


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _NotConfigured() from None


def _settings() -> _Settings:
    return _Settings()  # type: ignore[call-arg]


def _adform_client(settings: _Settings) -> DspDeliveryClient:
    if not settings.adform_client_id or settings.adform_client_secret is None:
        raise _NotConfigured()
    return AdformDeliveryClient(
        client_id=settings.adform_client_id,
        client_secret=settings.adform_client_secret,
        http_client=httpx.Client(timeout=httpx.Timeout(30.0)),
        today=lambda: local_today(settings.app_timezone),
    )


def _run_locked(
    engine: Engine,
    session_factory: Callable[[], Session],
    client: DspDeliveryClient,
    today: date,
    out: Callable[[str], None],
    custom_window: DeliveryDateRange | None = None,
) -> int:
    # The lock lives on its own connection for the whole run and goes with it, even if the process dies.
    with engine.connect() as lock_connection:
        acquired = lock_connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": NIGHTLY_INGESTION_LOCK_KEY}
        ).scalar()
        if not acquired:
            out("status: another run is in progress")
            return EXIT_ALREADY_RUNNING
        try:
            return _run(session_factory, client, today, out, custom_window)
        finally:
            lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": NIGHTLY_INGESTION_LOCK_KEY})
            lock_connection.commit()


def _run(
    session_factory: Callable[[], Session],
    client: DspDeliveryClient,
    today: date,
    out: Callable[[str], None],
    custom_window: DeliveryDateRange | None = None,
) -> int:
    try:
        dsp_id = _adform_dsp_id(session_factory)
    except _NotConfigured:
        out("status: not configured")
        return EXIT_NOT_CONFIGURED

    service = DeliveryIngestionService(
        dsp_client=client,
        unit_of_work_factory=lambda: SqlAlchemyUnitOfWork(session_factory),
        clock=lambda: utc_now().replace(tzinfo=None),
    )
    try:
        result = service.run(dsp_id, today, route=IngestionRoute.API, window=custom_window)
        # A custom range says nothing about the rolling window the absence rule looks at.
        absences = None if custom_window else service.detect_missing_delivery(dsp_id, today, result.batch_id)
        new_exceptions = _new_unmatched_exceptions(session_factory, result.batch_id)
    except Exception as error:  # noqa: BLE001 - the class name is all that is reported
        out("status: failed")
        out(f"error: {type(error).__name__}")
        return EXIT_FAILED

    out("status: succeeded")
    out(f"rows_read: {result.rows_read}")
    out(f"ignored_rows: {result.ignored_row_count}")
    out(f"zero_unmatched_rows: {result.zero_unmatched_row_count}")
    out(f"new_exceptions: {new_exceptions}")
    out(f"mapped_lines: {result.mapped_line_count}")
    out(f"skipped_lines: {len(result.skipped_line_ids)}")
    out(f"absences: {absences}" if absences is not None else "absences: skipped, custom range")
    return EXIT_SUCCEEDED


def _adform_dsp_id(session_factory: Callable[[], Session]) -> int:
    session = session_factory()
    try:
        dsp_id = session.scalar(select(DSPRecord.id).where(DSPRecord.name == _DSP_NAME))
    finally:
        session.close()
    if dsp_id is None:
        raise _NotConfigured()
    return dsp_id


def _new_unmatched_exceptions(session_factory: Callable[[], Session], batch_id: int) -> int:
    """Unmatched-delivery exceptions this batch opened: a pair seen before keeps the batch that first saw it."""
    session = session_factory()
    try:
        return int(session.scalar(
            select(func.count()).select_from(IngestionExceptionRecord).where(
                IngestionExceptionRecord.ingestion_batch_id == batch_id,
                IngestionExceptionRecord.exception_type == "unmatched_delivery",
            )
        ) or 0)
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
