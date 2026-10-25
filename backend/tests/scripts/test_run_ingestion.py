"""The nightly command against PostgreSQL: exit codes, the lock, atomic failure and an idempotent window."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text

from app.domain.exceptions import DspUnreachableError
from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey
from app.infrastructure.persistence.models.delivery import (
    DailyDeliveryRecord,
    IngestionBatchRecord,
    IngestionExceptionRecord,
)
from app.infrastructure.persistence.models.masters import DSPRecord
from scripts.run_ingestion import NIGHTLY_INGESTION_LOCK_KEY, main
from tests.fixtures.delivery_data import (
    add_line_to_campaign,
    insert_campaign_line,
    insert_mapping,
    replace_flights,
)
from tests.fixtures.delivery_rows import dsp_row
from tests.fixtures.dsp_delivery_client import InMemoryDspDeliveryClient

D5 = date(2026, 8, 5)
MAPPED = ExternalLineKey("1001", "2001")
ABSENT = ExternalLineKey("1002", "2002")
STRANGER = ExternalLineKey("9", "9")


class FailsAfterTwoRows(InMemoryDspDeliveryClient):
    """Streams some rows and then fails with a message that must never reach the output."""

    def fetch_delivery(self, date_range: DeliveryDateRange) -> Iterator[DspDeliveryRow]:
        for index, row in enumerate(super().fetch_delivery(date_range)):
            if index == 2:
                raise DspUnreachableError("Adform said: token secret-token for account ACME-42 expired")
            yield row


class Scenario:
    """An Adform DSP, a mapped line that delivers and a mapped line whose only flight ended with no delivery."""

    def __init__(self, session, engine, rows=None, client_class=InMemoryDspDeliveryClient):
        self.session = session
        self.engine = engine
        dsp = DSPRecord(name="Adform", is_active=True)
        session.add(dsp)
        session.flush()
        self.dsp_id = dsp.id
        self.delivering_line = insert_campaign_line(session, campaign_name="Scenario", dsp_id=dsp.id)
        insert_mapping(session, self.delivering_line, dsp.id, "1001", "2001")
        self.absent_line = add_line_to_campaign(session, self.delivering_line, 2)
        replace_flights(session, self.absent_line, [(date(2026, 8, 1), date(2026, 8, 5))])
        insert_mapping(session, self.absent_line, dsp.id, "1002", "2002")
        self.client = client_class(rows if rows is not None else [
            dsp_row(D5, MAPPED, impressions=700),
            dsp_row(date(2026, 8, 6), MAPPED, impressions=300),
            dsp_row(D5, STRANGER, impressions=40),
            dsp_row(D5, ExternalLineKey("8", "8"), impressions=0, media_cost=Decimal("0")),
            dsp_row(D5, None, unattributed=True),
        ])
        # Committed, as a real database would hold it: the command opens and closes its own sessions.
        session.commit()
        self.output: list[str] = []

    def run(self, *arguments: str, client=None) -> int:
        return main(
            ["--date", "2026-08-10", *arguments], out=self.output.append, engine=self.engine,
            session_factory=lambda: self.session, client=client or self.client,
        )

    def count(self, record) -> int:
        return self.session.scalar(select(func.count()).select_from(record))

    def batch_statuses(self) -> list[str]:
        return list(self.session.scalars(select(IngestionBatchRecord.status).order_by(IngestionBatchRecord.id)))


@pytest.fixture
def scenario(rolled_back_session, test_engine):
    return Scenario(rolled_back_session, test_engine)


def test_a_successful_run_ingests_records_the_batch_and_detects_absence_with_its_id(scenario):
    assert scenario.run() == 0

    assert scenario.client.requested_ranges == [DeliveryDateRange(date(2026, 8, 3), date(2026, 8, 9))]
    assert scenario.count(DailyDeliveryRecord) == 2
    assert scenario.batch_statuses() == ["succeeded"]
    batch_id = scenario.session.scalar(select(IngestionBatchRecord.id))
    missing = scenario.session.scalars(
        select(IngestionExceptionRecord).where(IngestionExceptionRecord.exception_type == "missing_delivery")
    ).all()
    assert [(e.campaign_line_id, e.ingestion_batch_id) for e in missing] == [(scenario.absent_line, batch_id)]


def test_a_client_failure_marks_the_batch_failed_stores_no_partial_rows_and_exits_1(rolled_back_session, test_engine):
    scenario = Scenario(rolled_back_session, test_engine, client_class=FailsAfterTwoRows)

    assert scenario.run() == 1

    assert scenario.batch_statuses() == ["failed"]
    assert scenario.count(DailyDeliveryRecord) == 0
    assert scenario.count(IngestionExceptionRecord) == 0  # absence is not detected after a failed run


def test_a_second_run_while_the_lock_is_held_does_nothing_and_exits_2(scenario, test_engine):
    with test_engine.connect() as holder:
        assert holder.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": NIGHTLY_INGESTION_LOCK_KEY}).scalar()
        try:
            assert scenario.run() == 2
        finally:
            holder.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": NIGHTLY_INGESTION_LOCK_KEY})

    assert scenario.client.requested_ranges == []
    assert scenario.batch_statuses() == []


def test_the_lock_is_released_when_the_run_ends(scenario, test_engine):
    assert scenario.run() == 0

    with test_engine.connect() as other:
        acquired = other.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": NIGHTLY_INGESTION_LOCK_KEY}).scalar()
        other.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": NIGHTLY_INGESTION_LOCK_KEY})
    assert acquired is True


def test_the_lock_is_released_when_the_run_fails(rolled_back_session, test_engine):
    scenario = Scenario(rolled_back_session, test_engine, client_class=FailsAfterTwoRows)
    assert scenario.run() == 1

    with test_engine.connect() as other:
        acquired = other.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": NIGHTLY_INGESTION_LOCK_KEY}).scalar()
        other.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": NIGHTLY_INGESTION_LOCK_KEY})
    assert acquired is True


def test_missing_adform_credentials_exit_3_before_any_batch(scenario, monkeypatch):
    monkeypatch.delenv("ADFORM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ADFORM_CLIENT_SECRET", raising=False)

    code = main(["--date", "2026-08-10"], out=scenario.output.append, engine=scenario.engine,
                session_factory=lambda: scenario.session)

    assert code == 3
    assert scenario.batch_statuses() == []


def test_an_unknown_time_zone_exits_3(scenario, monkeypatch):
    monkeypatch.setenv("APP_TIMEZONE", "Not/AZone")

    assert scenario.run() == 3
    assert scenario.batch_statuses() == []


def test_a_malformed_date_exits_3(scenario):
    code = main(["--date", "10/08/2026"], out=scenario.output.append, engine=scenario.engine,
                session_factory=lambda: scenario.session, client=scenario.client)

    assert code == 3
    assert scenario.batch_statuses() == []


def test_a_missing_database_url_exits_3(scenario, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code = main(["--date", "2026-08-10"], out=scenario.output.append, client=scenario.client)

    assert code == 3


def test_without_an_adform_dsp_row_the_run_exits_3(rolled_back_session, test_engine):
    scenario = Scenario(rolled_back_session, test_engine)
    scenario.session.execute(text("UPDATE dsps SET name = 'Something else' WHERE name = 'Adform'"))

    assert scenario.run() == 3
    assert scenario.batch_statuses() == []


def test_repeating_the_same_window_changes_no_row_and_no_exception(scenario):
    assert scenario.run() == 0
    first = (scenario.count(DailyDeliveryRecord), scenario.count(IngestionExceptionRecord))
    totals = scenario.session.scalar(select(func.sum(DailyDeliveryRecord.impressions)))

    assert scenario.run() == 0

    assert (scenario.count(DailyDeliveryRecord), scenario.count(IngestionExceptionRecord)) == first
    assert scenario.session.scalar(select(func.sum(DailyDeliveryRecord.impressions))) == totals
    assert scenario.batch_statuses() == ["succeeded", "succeeded"]


def test_the_date_option_replaces_today_and_the_clock_decides_otherwise(scenario):
    # 00:30 on 11 August in Madrid is still the 10th in UTC: the window ends on the 10th.
    code = main(
        [], out=scenario.output.append, engine=scenario.engine, session_factory=lambda: scenario.session,
        client=scenario.client, now=lambda: datetime(2026, 8, 10, 22, 30, tzinfo=UTC),
    )

    assert code == 0
    assert scenario.client.requested_ranges == [DeliveryDateRange(date(2026, 8, 4), date(2026, 8, 10))]


def test_there_is_no_dry_run_option_and_an_unknown_option_exits_3_not_2(scenario):
    # Argparse's own exit code would be 2, which here means "another run holds the lock".
    code = main(["--dry-run"], out=scenario.output.append, engine=scenario.engine, client=scenario.client)

    assert code == 3
    assert scenario.client.requested_ranges == []


def test_the_output_shows_how_many_lines_are_mapped(scenario):
    assert scenario.run() == 0

    assert "mapped_lines: 2" in scenario.output


def test_a_run_with_no_mapped_line_records_the_batch_fills_the_catalogue_and_says_so(scenario):
    from app.infrastructure.persistence.models.dsp_catalog import DspCatalogLineRecord
    from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord
    from tests.fixtures.delivery_rows import catalog_info

    scenario.session.query(DSPMappingRecord).delete()
    scenario.session.commit()
    scenario.client = InMemoryDspDeliveryClient([dsp_row(D5, STRANGER, impressions=40, catalog=catalog_info())])

    assert scenario.run() == 0

    assert "mapped_lines: 0" in scenario.output
    assert scenario.batch_statuses() == ["succeeded"]
    assert scenario.count(DspCatalogLineRecord) == 1
    assert len(scenario.client.requested_ranges) == 1
