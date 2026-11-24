"""The nightly command against PostgreSQL: exit codes, the lock, atomic failure and an idempotent window."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.domain.exceptions import DspUnreachableError
from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey
from app.infrastructure.persistence.models.delivery import (
    DailyDeliveryRecord,
    IngestionBatchRecord,
    IngestionExceptionRecord,
)
from app.infrastructure.dsp.equativ_delivery_client import EquativDeliveryClient
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
from tests.fixtures.fake_equativ import REPORT_ID, FakeEquativ, package_row

D5 = date(2026, 8, 5)
MAPPED = ExternalLineKey("1001", "2001")
ABSENT = ExternalLineKey("1002", "2002")
STRANGER = ExternalLineKey("9", "9")
_LOCK = "SELECT pg_try_advisory_lock(:namespace, :dsp_id)"
_UNLOCK = "SELECT pg_advisory_unlock(:namespace, :dsp_id)"


class FailsAfterTwoRows(InMemoryDspDeliveryClient):
    """Streams some rows and then fails with a message that must never reach the output."""

    def fetch_delivery(self, date_range: DeliveryDateRange) -> Iterator[DspDeliveryRow]:
        for index, row in enumerate(super().fetch_delivery(date_range)):
            if index == 2:
                raise DspUnreachableError("Adform said: token secret-token for account ACME-42 expired")
            yield row


@contextmanager
def held_lock(engine: Engine, dsp_id: int) -> Iterator[None]:
    """Hold the lock of one DSP's runs from another connection, as a run still going would."""
    with engine.connect() as holder:
        assert holder.execute(text(_LOCK), {"namespace": NIGHTLY_INGESTION_LOCK_KEY, "dsp_id": dsp_id}).scalar()
        try:
            yield
        finally:
            holder.execute(text(_UNLOCK), {"namespace": NIGHTLY_INGESTION_LOCK_KEY, "dsp_id": dsp_id})


def lock_is_free(engine: Engine, dsp_id: int) -> bool:
    with engine.connect() as other:
        acquired = other.execute(text(_LOCK), {"namespace": NIGHTLY_INGESTION_LOCK_KEY, "dsp_id": dsp_id}).scalar()
        if acquired:
            other.execute(text(_UNLOCK), {"namespace": NIGHTLY_INGESTION_LOCK_KEY, "dsp_id": dsp_id})
    return bool(acquired)


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
    with held_lock(test_engine, scenario.dsp_id):
        assert scenario.run() == 2

    assert scenario.client.requested_ranges == []
    assert scenario.batch_statuses() == []


def test_the_lock_is_released_when_the_run_ends(scenario, test_engine):
    assert scenario.run() == 0

    assert lock_is_free(test_engine, scenario.dsp_id)


def test_the_lock_is_released_when_the_run_fails(rolled_back_session, test_engine):
    scenario = Scenario(rolled_back_session, test_engine, client_class=FailsAfterTwoRows)
    assert scenario.run() == 1

    assert lock_is_free(test_engine, scenario.dsp_id)


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


# --- --dsp, the lock per DSP and the 06:00 UTC rule of Equativ ------------------------------------------------------

EQUATIV_TODAY = "2026-11-24"
EQUATIV_WINDOW = DeliveryDateRange(date(2026, 11, 17), date(2026, 11, 23))
PACKAGE = "900000001"
SILENT_PACKAGE = "900000002"
UNMAPPED_PACKAGE = "900000009"


def equativ_client(fake: FakeEquativ) -> EquativDeliveryClient:
    """The real client over the synthetic Equativ; it never sleeps and its clock never moves."""
    return EquativDeliveryClient(
        "synthetic-equativ-client-id", "synthetic-equativ-client-secret", fake.client(),
        sleep=lambda _: None, monotonic=lambda: 0.0,
    )


class EquativScenario:
    """An Adform line and two Equativ lines: one whose package delivers and one whose flight ended without delivery."""

    def __init__(self, session: Session, engine: Engine, fake: FakeEquativ | None = None) -> None:
        self.session = session
        self.engine = engine
        adform = DSPRecord(name="Adform", is_active=True)
        equativ = DSPRecord(name="Equativ", is_active=True)
        session.add_all([adform, equativ])
        session.flush()
        self.adform_id, self.equativ_id = adform.id, equativ.id
        start, end = date(2026, 11, 1), date(2026, 11, 30)
        self.adform_line = insert_campaign_line(session, "Adform side", start, end, dsp_id=adform.id)
        insert_mapping(session, self.adform_line, adform.id, "1001", "2001")
        self.deal_line = insert_campaign_line(session, "Equativ side", start, end, dsp_id=equativ.id)
        insert_mapping(session, self.deal_line, equativ.id, PACKAGE, PACKAGE)
        self.silent_line = add_line_to_campaign(session, self.deal_line, 2)
        replace_flights(session, self.silent_line, [(date(2026, 11, 1), date(2026, 11, 20))])
        insert_mapping(session, self.silent_line, equativ.id, SILENT_PACKAGE, SILENT_PACKAGE)
        self.fake = fake or FakeEquativ(rows=[
            package_row(day="2026-11-19T00:00:00", package_id=PACKAGE, impressions="61628"),
            package_row(day="2026-11-20T00:00:00", package_id=PACKAGE, impressions="1000"),
            package_row(day="2026-11-20T00:00:00", package_id=UNMAPPED_PACKAGE, impressions="40"),
        ])
        session.commit()
        self.output: list[str] = []

    def run(
        self, *arguments: str, now: datetime = datetime(2026, 11, 24, 7, 0, tzinfo=UTC),
        client: DspDeliveryClient | None = None,
    ) -> int:
        return main(
            list(arguments), out=self.output.append, engine=self.engine, session_factory=lambda: self.session,
            client=client or equativ_client(self.fake), now=lambda: now,
        )

    def batches(self) -> list[IngestionBatchRecord]:
        return list(self.session.scalars(select(IngestionBatchRecord).order_by(IngestionBatchRecord.id)))

    def delivered_lines(self) -> set[int]:
        return set(self.session.scalars(select(DailyDeliveryRecord.campaign_line_id)))

    def count_deliveries(self) -> int:
        return int(self.session.scalar(select(func.count()).select_from(DailyDeliveryRecord)) or 0)

    def missing_delivery(self) -> list[tuple[int | None, int]]:
        return [
            (e.campaign_line_id, e.ingestion_batch_id)
            for e in self.session.scalars(
                select(IngestionExceptionRecord).where(IngestionExceptionRecord.exception_type == "missing_delivery")
            )
        ]


@pytest.fixture
def equativ(rolled_back_session: Session, test_engine: Engine) -> EquativScenario:
    return EquativScenario(rolled_back_session, test_engine)


def test_without_dsp_the_run_ingests_adform_as_before(equativ: EquativScenario) -> None:
    adform = InMemoryDspDeliveryClient([dsp_row(date(2026, 11, 19), MAPPED, impressions=700)])

    assert equativ.run("--date", EQUATIV_TODAY, client=adform) == 0

    (batch,) = equativ.batches()
    assert (batch.dsp_id, batch.status, batch.source_file) == (equativ.adform_id, "succeeded", None)
    assert equativ.delivered_lines() == {equativ.adform_line}
    assert "mapped_lines: 1" in equativ.output


def test_dsp_equativ_ingests_only_the_equativ_lines_and_records_the_report_as_the_source(
    equativ: EquativScenario,
) -> None:
    assert equativ.run("--dsp", "Equativ", "--date", EQUATIV_TODAY) == 0

    (batch,) = equativ.batches()
    assert (batch.dsp_id, batch.route, batch.status) == (equativ.equativ_id, "api", "succeeded")
    assert (batch.window_start, batch.window_end) == (EQUATIV_WINDOW.start, EQUATIV_WINDOW.end)
    assert batch.source_file == REPORT_ID
    assert equativ.delivered_lines() == {equativ.deal_line}
    assert equativ.session.scalar(select(func.sum(DailyDeliveryRecord.impressions))) == 62628
    assert "mapped_lines: 2" in equativ.output
    assert len(equativ.fake.created_reports()) == 1


@pytest.mark.parametrize(
    "fake",
    [
        FakeEquativ(rows=[package_row(package_id=PACKAGE)], statuses=["PubSubPublishSuccessful", "ReportGenerationFailed"]),
        FakeEquativ(rows=[package_row(package_id=PACKAGE)], total_rows=2),
    ],
    ids=["failed-wait", "short-preview"],
)
def test_an_equativ_run_that_fails_after_its_report_was_created_names_the_report_on_its_failed_batch(
    rolled_back_session: Session, test_engine: Engine, fake: FakeEquativ
) -> None:
    scenario = EquativScenario(rolled_back_session, test_engine, fake=fake)

    assert scenario.run("--dsp", "Equativ", "--date", EQUATIV_TODAY) == 1

    (batch,) = scenario.batches()
    assert (batch.status, batch.source_file) == ("failed", REPORT_ID)
    assert scenario.count_deliveries() == 0
    assert scenario.missing_delivery() == []


@pytest.mark.parametrize("name", ["Displayce", "Unknown DSP", "equativ"])
def test_a_dsp_without_a_connector_exits_3_with_no_batch(
    rolled_back_session: Session, test_engine: Engine, name: str
) -> None:
    scenario = EquativScenario(rolled_back_session, test_engine)
    scenario.session.add(DSPRecord(name="Displayce", is_active=True))
    scenario.session.commit()

    assert main(["--dsp", name, "--date", EQUATIV_TODAY], out=scenario.output.append, engine=test_engine,
                session_factory=lambda: scenario.session) == 3

    assert scenario.batches() == []
    assert scenario.output == ["status: not configured"]


def test_missing_equativ_credentials_exit_3_with_no_batch(
    equativ: EquativScenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EQUATIV_CLIENT_ID", raising=False)
    monkeypatch.delenv("EQUATIV_CLIENT_SECRET", raising=False)

    assert main(["--dsp", "Equativ", "--date", EQUATIV_TODAY], out=equativ.output.append, engine=equativ.engine,
                session_factory=lambda: equativ.session) == 3

    assert equativ.batches() == []


def test_with_equativ_credentials_the_run_builds_the_equativ_client(
    equativ: EquativScenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No client is injected: the command builds its own, and the guard of the test suite stops it at Equativ's door.
    monkeypatch.setenv("EQUATIV_CLIENT_ID", "synthetic-equativ-client-id")
    monkeypatch.setenv("EQUATIV_CLIENT_SECRET", "synthetic-equativ-client-secret")

    assert main(["--dsp", "Equativ", "--date", EQUATIV_TODAY], out=equativ.output.append, engine=equativ.engine,
                session_factory=lambda: equativ.session) == 1

    (batch,) = equativ.batches()
    assert (batch.dsp_id, batch.status, batch.source_file) == (equativ.equativ_id, "failed", None)
    assert "error: RealEquativRequestBlocked" in equativ.output


def test_a_second_run_of_the_same_dsp_while_its_lock_is_held_exits_2(equativ: EquativScenario) -> None:
    with held_lock(equativ.engine, equativ.equativ_id):
        assert equativ.run("--dsp", "Equativ", "--date", EQUATIV_TODAY) == 2

    assert equativ.batches() == []
    assert equativ.fake.requests == []


def test_an_equativ_run_proceeds_while_an_adform_run_holds_its_lock(equativ: EquativScenario) -> None:
    with held_lock(equativ.engine, equativ.adform_id):
        assert equativ.run("--dsp", "Equativ", "--date", EQUATIV_TODAY) == 0

    assert [batch.status for batch in equativ.batches()] == ["succeeded"]
    assert lock_is_free(equativ.engine, equativ.equativ_id)


def test_an_equativ_run_started_before_06_00_utc_ingests_and_skips_the_absence_detection(
    equativ: EquativScenario,
) -> None:
    assert equativ.run("--dsp", "Equativ", now=datetime(2026, 11, 24, 5, 59, tzinfo=UTC)) == 0

    assert [batch.status for batch in equativ.batches()] == ["succeeded"]
    assert equativ.delivered_lines() == {equativ.deal_line}
    assert equativ.missing_delivery() == []
    assert "absences: skipped, before 06:00 UTC" in equativ.output


def test_an_equativ_run_started_at_06_00_utc_detects_absence_with_its_batch_id(equativ: EquativScenario) -> None:
    assert equativ.run("--dsp", "Equativ", now=datetime(2026, 11, 24, 6, 0, tzinfo=UTC)) == 0

    (batch,) = equativ.batches()
    assert equativ.missing_delivery() == [(equativ.silent_line, batch.id)]
    assert "absences: 1" in equativ.output


def test_an_adform_run_detects_absence_whatever_the_hour(scenario: Scenario) -> None:
    code = main(
        [], out=scenario.output.append, engine=scenario.engine, session_factory=lambda: scenario.session,
        client=scenario.client, now=lambda: datetime(2026, 8, 10, 3, 0, tzinfo=UTC),
    )

    assert code == 0
    assert "absences: 1" in scenario.output
