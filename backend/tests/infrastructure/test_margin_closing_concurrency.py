"""Two closings of the same month at the same time: each flight ends with exactly one row and both succeed; and an
edit of the month that waited for a closing finds its flight frozen.

This needs real commits from two connections, so it runs on a throwaway database migrated to head.
"""

import threading
import time
from datetime import date, datetime
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.application.services.billing_adjustment_service import BillingAdjustmentService
from app.application.services.margin_closing_service import ClosingResult, MarginClosingService
from app.domain.exceptions import BillingAdjustmentError
from app.domain.value_objects.billing import BillingBasis
from app.infrastructure.persistence.models.campaign import CampaignLinePeriodRecord
from app.infrastructure.persistence.models.margin import (
    AppliedRateRecord,
    ClosedFlightSnapshotRecord,
    FlightBillingAdjustmentRecord,
    MonthClosingRecord,
)
from app.infrastructure.persistence.repositories.sqlalchemy_billing_adjustment_repository import (
    SqlAlchemyBillingAdjustmentTransaction,
)
from app.infrastructure.persistence.repositories.sqlalchemy_margin_repositories import (
    SqlAlchemyMarginClosingTransaction,
)
from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL
from tests.fixtures.delivery_data import add_line_to_campaign, insert_campaign_line, insert_user
from tests.fixtures.margin_data import make_month_closable

SCRATCH_DB = "adops360_margin_concurrency_test"
LINES = 4


@pytest.fixture
def scratch_engine(monkeypatch):
    admin = create_engine(make_url(TEST_DATABASE_URL).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    url = make_url(TEST_DATABASE_URL).set(database=SCRATCH_DB)
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head")
    engine = create_engine(url, pool_size=5)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def test_two_concurrent_closings_of_one_month_leave_one_row_per_flight(scratch_engine):
    with Session(scratch_engine) as setup:
        first = insert_campaign_line(setup)
        for number in range(2, LINES + 1):
            add_line_to_campaign(setup, first, number)
        user_id = insert_user(setup, "concurrent@example.com")
        make_month_closable(setup, 2026, 8, user_id, date(2026, 9, 1))
        setup.commit()

    start = threading.Barrier(2)
    results: list[ClosingResult | BaseException] = []

    def close() -> None:
        with Session(scratch_engine) as session:
            service = MarginClosingService(
                SqlAlchemyMarginClosingTransaction(session),
                today=lambda: date(2026, 9, 1), now=lambda: datetime(2026, 9, 1, 8, 0),
            )
            start.wait()
            try:
                results.append(service.close_month(2026, 8, user_id))
            except BaseException as error:  # noqa: BLE001 - the test reports it
                results.append(error)

    threads = [threading.Thread(target=close) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert all(isinstance(result, ClosingResult) for result in results), results
    assert sorted(result.closed for result in results) == [0, LINES]
    assert [result.closings for result in results if isinstance(result, ClosingResult)] == [1, 1]
    with Session(scratch_engine) as check:
        assert check.scalar(select(func.count()).select_from(AppliedRateRecord)) == LINES
        assert check.scalar(select(func.count(func.distinct(AppliedRateRecord.campaign_line_period_id)))) == LINES
        assert check.scalar(select(func.count()).select_from(ClosedFlightSnapshotRecord)) == LINES
        assert check.scalar(select(func.count(func.distinct(ClosedFlightSnapshotRecord.applied_rate_id)))) == LINES
        assert check.scalar(select(func.count()).select_from(MonthClosingRecord)) == 1


class _HeldClosing(SqlAlchemyMarginClosingTransaction):
    """A closing that tells when it holds the month's lock and waits for leave to commit, still holding it."""

    def __init__(self, session: Session, holding: threading.Event, release: threading.Event) -> None:
        super().__init__(session)
        self._holding, self._release = holding, release

    def lock_month(self, year: int, month: int) -> None:
        super().lock_month(year, month)
        self._holding.set()

    def commit(self) -> None:
        assert self._release.wait(timeout=30)
        super().commit()


def _a_lock_is_awaited(engine: Engine) -> bool:
    with engine.connect() as connection:
        return bool(connection.scalar(text(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"
        )))


def test_an_adjustment_that_waited_for_the_closing_of_its_month_finds_its_flight_closed(scratch_engine: Engine) -> None:
    with Session(scratch_engine) as setup:
        line_id = insert_campaign_line(setup)
        user_id = insert_user(setup, "waiting@example.com")
        flight_id = setup.scalars(
            select(CampaignLinePeriodRecord.id).where(CampaignLinePeriodRecord.campaign_line_id == line_id)
        ).one()
        make_month_closable(setup, 2026, 8, user_id, date(2026, 9, 1))
        setup.commit()

    holding, release = threading.Event(), threading.Event()
    outcome: dict[str, object] = {}

    def close() -> None:
        with Session(scratch_engine) as session:
            service = MarginClosingService(
                _HeldClosing(session, holding, release), today=lambda: date(2026, 9, 1),
                now=lambda: datetime(2026, 9, 1, 8, 0),
            )
            outcome["closing"] = service.close_month(2026, 8, user_id)

    def adjust() -> None:
        with Session(scratch_engine) as session:
            service = BillingAdjustmentService(
                SqlAlchemyBillingAdjustmentTransaction(session), today=lambda: date(2026, 9, 1),
                now=lambda: datetime(2026, 9, 1, 8, 1),
            )
            try:
                service.adjust(flight_id, BillingBasis.CUSTOM, Decimal("4200.00"), "Agreed with the agency", user_id)
            except BillingAdjustmentError as error:
                outcome["adjustment"] = error.code
            else:
                outcome["adjustment"] = "written"

    closing = threading.Thread(target=close)
    closing.start()
    assert holding.wait(timeout=30)
    adjusting = threading.Thread(target=adjust)
    adjusting.start()
    deadline = time.monotonic() + 30
    while not _a_lock_is_awaited(scratch_engine):  # the adjustment waits on the month's lock the closing holds
        assert time.monotonic() < deadline, "the adjustment never waited for the closing's lock"
        time.sleep(0.05)
    release.set()
    closing.join(timeout=30)
    adjusting.join(timeout=30)

    assert isinstance(outcome["closing"], ClosingResult) and outcome["closing"].closed == 1
    assert outcome["adjustment"] == "flight_closed"
    with Session(scratch_engine) as check:
        assert check.scalar(select(func.count()).select_from(FlightBillingAdjustmentRecord)) == 0
