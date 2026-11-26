"""The nightly ingestion: one command for the host scheduler, using the same service as every other route.

Calculates the window for today (in the configured time zone, or --date), ingests the lines with a validated
mapping on one DSP with one request, records the batch, and then detects absence with that batch's id. --dsp names
the DSP, Adform when absent; only a DSP with a connector (Adform, Equativ) is accepted. A PostgreSQL advisory lock
per DSP stops two runs of one DSP overlapping, while runs of different DSPs may. An Equativ run started before
06:00 UTC still ingests but skips the absence detection: Equativ may not have closed the previous UTC day yet.

Exit codes: 0 the batch succeeded; 1 it failed; 2 another run holds the lock; 3 configuration is missing.

It prints states and counts only: never an identifier, a name, an amount, a token or the text of a DSP error;
a failure is summarised by the name of its error class. A succeeded run also prints `closed_month_days`, how many days
of its window fall in a month that holds a closing header: those days are ingested like any other, and a closed
flight only gets the warning that its delivery changed.

A custom range, --from YYYY-MM-DD --to YYYY-MM-DD, replaces the rolling window with one request for the whole
range (at most 31 days, ending no later than yesterday in the configured zone). It uses the same service and the
same idempotent replacement, records the range on the batch and skips the absence detection. It cannot be combined
with --date, and invalid arguments exit with 3 like every other configuration problem.

Run: python -m scripts.run_ingestion [--dsp NAME] [--date YYYY-MM-DD | --from YYYY-MM-DD --to YYYY-MM-DD]
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
from app.domain.services.closed_months import days_in_closed_months
from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.services.local_calendar import local_today, utc_now
from app.domain.value_objects.delivery import DeliveryDateRange
from app.infrastructure.dsp.adform_delivery_client import AdformDeliveryClient
from app.infrastructure.dsp.equativ_delivery_client import EquativDeliveryClient
from app.infrastructure.persistence.database import build_engine, build_session_factory
from app.infrastructure.persistence.models.delivery import IngestionExceptionRecord
from app.infrastructure.persistence.models.margin import MonthClosingRecord
from app.infrastructure.persistence.models.masters import DSPRecord
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

EXIT_SUCCEEDED, EXIT_FAILED, EXIT_ALREADY_RUNNING, EXIT_NOT_CONFIGURED = 0, 1, 2, 3
# Arbitrary but fixed: the first key of the session-level advisory lock of every run; the second is the DSP's id.
NIGHTLY_INGESTION_LOCK_KEY = 0x41444F50
DEFAULT_DSP = "Adform"
EQUATIV = "Equativ"
# Before this hour Equativ may not have closed the previous UTC day, so its absence detection waits.
EQUATIV_ABSENCE_FROM_HOUR_UTC = 6
MAX_RANGE_DAYS = 31


class _NotConfigured(Exception):
    """Something the run needs is missing or malformed. Carries no detail: the output never echoes values."""


class _Settings(BaseSettings):
    """Only what this command reads, so it does not need the Entra settings of the API."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    database_url: str
    app_timezone: str = "Europe/Madrid"
    adform_client_id: str | None = None
    adform_client_secret: SecretStr | None = None
    equativ_client_id: str | None = None
    equativ_client_secret: SecretStr | None = None


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
    started_at = now()
    try:
        arguments = _parse(argv)
        settings = _settings()
        # Evaluated even with --date, so a mistyped time zone is caught on every run.
        zone_today = local_today(settings.app_timezone, now)
        today = arguments.date or zone_today
        custom_window = _custom_window(arguments, zone_today)
        build_client = _CLIENT_BUILDERS.get(arguments.dsp)
        if build_client is None:
            raise _NotConfigured()
        dsp_client = client or build_client(settings)
    except (_NotConfigured, ValidationError, ValueError):
        out("status: not configured")
        return EXIT_NOT_CONFIGURED

    own_engine = engine is None
    engine = engine or build_engine(settings.database_url)
    try:
        sessions = session_factory or build_session_factory(engine)
        try:
            dsp_id = _dsp_id(sessions, arguments.dsp)
        except _NotConfigured:
            out("status: not configured")
            return EXIT_NOT_CONFIGURED
        absence_skipped = _absence_skipped(arguments.dsp, started_at, custom_window)
        return _run_locked(engine, sessions, dsp_id, dsp_client, today, out, custom_window, absence_skipped)
    finally:
        if own_engine:
            engine.dispose()


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _Parser(prog="run_ingestion", description="Run the nightly ingestion of one DSP.")
    parser.add_argument("--dsp", default=DEFAULT_DSP, help="the DSP to ingest: Adform (default) or Equativ")
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


def _equativ_client(settings: _Settings) -> DspDeliveryClient:
    if not settings.equativ_client_id or settings.equativ_client_secret is None:
        raise _NotConfigured()
    return EquativDeliveryClient(
        client_id=settings.equativ_client_id,
        client_secret=settings.equativ_client_secret,
        http_client=httpx.Client(timeout=httpx.Timeout(30.0)),
    )


# The DSPs with a connector. Any other name, Displayce included, is a configuration error.
_CLIENT_BUILDERS: dict[str, Callable[[_Settings], DspDeliveryClient]] = {
    DEFAULT_DSP: _adform_client,
    EQUATIV: _equativ_client,
}


def _absence_skipped(dsp_name: str, started_at: datetime, custom_window: DeliveryDateRange | None) -> str | None:
    """Why the absence detection does not run, None when it does."""
    if custom_window is not None:
        # A custom range says nothing about the rolling window the absence rule looks at.
        return "custom range"
    if dsp_name == EQUATIV and started_at.astimezone(UTC).hour < EQUATIV_ABSENCE_FROM_HOUR_UTC:
        return f"before {EQUATIV_ABSENCE_FROM_HOUR_UTC:02d}:00 UTC"
    return None


def _run_locked(
    engine: Engine,
    session_factory: Callable[[], Session],
    dsp_id: int,
    client: DspDeliveryClient,
    today: date,
    out: Callable[[str], None],
    custom_window: DeliveryDateRange | None,
    absence_skipped: str | None,
) -> int:
    # The lock lives on its own connection for the whole run and goes with it, even if the process dies.
    lock_keys = {"namespace": NIGHTLY_INGESTION_LOCK_KEY, "dsp_id": dsp_id}
    with engine.connect() as lock_connection:
        acquired = lock_connection.execute(text("SELECT pg_try_advisory_lock(:namespace, :dsp_id)"), lock_keys).scalar()
        if not acquired:
            out("status: another run is in progress")
            return EXIT_ALREADY_RUNNING
        try:
            return _run(session_factory, dsp_id, client, today, out, custom_window, absence_skipped)
        finally:
            lock_connection.execute(text("SELECT pg_advisory_unlock(:namespace, :dsp_id)"), lock_keys)
            lock_connection.commit()


def _run(
    session_factory: Callable[[], Session],
    dsp_id: int,
    client: DspDeliveryClient,
    today: date,
    out: Callable[[str], None],
    custom_window: DeliveryDateRange | None,
    absence_skipped: str | None,
) -> int:
    service = DeliveryIngestionService(
        dsp_client=client,
        unit_of_work_factory=lambda: SqlAlchemyUnitOfWork(session_factory),
        clock=lambda: utc_now().replace(tzinfo=None),
    )
    try:
        result = service.run(dsp_id, today, route=IngestionRoute.API, window=custom_window)
        absences = None if absence_skipped else service.detect_missing_delivery(dsp_id, today, result.batch_id)
        new_exceptions = _new_unmatched_exceptions(session_factory, result.batch_id)
        closed_month_days = days_in_closed_months(result.window, _closed_months(session_factory, result.window))
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
    out(f"absences: {absences}" if absences is not None else f"absences: skipped, {absence_skipped}")
    out(f"closed_month_days: {closed_month_days}")
    return EXIT_SUCCEEDED


def _dsp_id(session_factory: Callable[[], Session], dsp_name: str) -> int:
    session = session_factory()
    try:
        dsp_id = session.scalar(select(DSPRecord.id).where(DSPRecord.name == dsp_name))
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


def _closed_months(session_factory: Callable[[], Session], window: DeliveryDateRange) -> set[tuple[int, int]]:
    """The (year, month) of the window's years that hold at least one closing header, read after the run. Only the
    days inside the window are counted from them."""
    session = session_factory()
    try:
        return {
            (year, month)
            for year, month in session.execute(
                select(MonthClosingRecord.period_year, MonthClosingRecord.period_month)
                .where(MonthClosingRecord.period_year.between(window.start.year, window.end.year))
                .distinct()
            )
        }
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
