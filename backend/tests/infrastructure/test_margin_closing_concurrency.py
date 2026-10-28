"""Two closings of the same month at the same time: each flight ends with exactly one row and both succeed.

This needs real commits from two connections, so it runs on a throwaway database migrated to head.
"""

import threading
from datetime import date, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.application.services.margin_closing_service import ClosingResult, MarginClosingService
from app.infrastructure.persistence.models.margin import AppliedRateRecord
from app.infrastructure.persistence.repositories.sqlalchemy_margin_repositories import (
    SqlAlchemyMarginClosingTransaction,
)
from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL
from tests.fixtures.delivery_data import add_line_to_campaign, insert_campaign_line, insert_user

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
    with Session(scratch_engine) as check:
        assert check.scalar(select(func.count()).select_from(AppliedRateRecord)) == LINES
        assert check.scalar(select(func.count(func.distinct(AppliedRateRecord.campaign_line_period_id)))) == LINES
