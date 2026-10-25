"""Every run leaves a batch behind: succeeded with its counts, or failed with no partial range."""

from collections.abc import Iterable, Iterator
from datetime import date

import pytest

from app.domain.entities.ingestion_batch import BatchStatus, IngestionRoute
from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.value_objects.delivery import DailyDelivery, DeliveryDateRange, DspDeliveryRow, ExternalLineKey
from app.domain.value_objects.ingestion import MappedLine
from tests.fixtures.delivery_rows import daily_delivery, dsp_row
from tests.fixtures.in_memory_delivery_repository import InMemoryDeliveryRepository
from tests.fixtures.ingestion_harness import DSP_ID, NOW, IngestionHarness

TODAY = date(2026, 8, 10)
LINE = 11
KEY = ExternalLineKey("100", "200")


class DspDown(Exception):
    """Stands in for any failure while the DSP report is being read."""


class FailingMidReportClient(DspDeliveryClient):
    def fetch_delivery(self, date_range: DeliveryDateRange) -> Iterator[DspDeliveryRow]:
        yield dsp_row(date(2026, 8, 5), KEY)
        raise DspDown()

    def resolve_identifiers(self, external_campaign_id: str, external_line_item_id: str) -> ExternalLineKey | None:
        return None


class RepositoryFailingOnInsert(InMemoryDeliveryRepository):
    """Seeded normally, then fails on the first insert of the run."""

    armed = False

    def add_all(self, deliveries: Iterable[DailyDelivery]) -> None:
        if not self.armed:
            super().add_all(deliveries)
            return
        for _ in deliveries:
            raise RuntimeError("insert failed")


def _only_batch(harness: IngestionHarness):
    assert len(harness.batches.records) == 1
    return next(iter(harness.batches.records.values()))


def test_a_successful_run_records_a_succeeded_batch_with_route_dsp_timings_and_row_count():
    harness = IngestionHarness(rows=[dsp_row(date(2026, 8, 5), KEY)], mapped_lines=[MappedLine(LINE, KEY)])

    result = harness.service.run(DSP_ID, TODAY)

    batch = _only_batch(harness)
    assert (batch.id, batch.dsp_id, batch.route, batch.status) == (result.batch_id, DSP_ID, IngestionRoute.API,
                                                                    BatchStatus.SUCCEEDED)
    assert (batch.started_at, batch.finished_at, batch.row_count) == (NOW, NOW, 1)


def test_every_delivery_references_the_batch_that_produced_it():
    harness = IngestionHarness(rows=[dsp_row(date(2026, 8, 5), KEY)], mapped_lines=[MappedLine(LINE, KEY)])

    result = harness.service.run(DSP_ID, TODAY)

    assert {row.ingestion_batch_id for row in harness.deliveries.rows.values()} == {result.batch_id}


def test_the_source_file_of_an_upload_is_recorded_on_the_batch():
    harness = IngestionHarness(mapped_lines=[MappedLine(LINE, KEY)])

    harness.service.run(DSP_ID, TODAY, route=IngestionRoute.UPLOAD, source_file="adform_2026-08-09.xlsx")

    batch = _only_batch(harness)
    assert (batch.route, batch.source_file) == (IngestionRoute.UPLOAD, "adform_2026-08-09.xlsx")


def test_a_run_that_fails_reading_the_report_leaves_a_failed_batch_and_the_previous_range():
    previous = daily_delivery(LINE, date(2026, 8, 5), impressions=1000)
    harness = IngestionHarness(mapped_lines=[MappedLine(LINE, KEY)], existing=[previous],
                               client=FailingMidReportClient())

    with pytest.raises(DspDown):
        harness.service.run(DSP_ID, TODAY)

    batch = _only_batch(harness)
    assert (batch.status, batch.finished_at, batch.row_count) == (BatchStatus.FAILED, NOW, 0)
    assert harness.deliveries.rows == {(LINE, date(2026, 8, 5)): previous}


def test_a_run_that_fails_while_storing_rolls_the_range_back_and_leaves_a_failed_batch():
    previous = daily_delivery(LINE, date(2026, 8, 5), impressions=1000)
    harness = IngestionHarness(rows=[dsp_row(date(2026, 8, 6), KEY)], mapped_lines=[MappedLine(LINE, KEY)],
                               existing=[previous])
    harness.deliveries = RepositoryFailingOnInsert([previous])
    harness.deliveries.armed = True

    with pytest.raises(RuntimeError):
        harness.service.run(DSP_ID, TODAY)

    assert _only_batch(harness).status is BatchStatus.FAILED
    assert harness.deliveries.rows == {(LINE, date(2026, 8, 5)): previous}


def test_the_original_error_reaches_the_caller_after_the_batch_is_recorded():
    harness = IngestionHarness(mapped_lines=[MappedLine(LINE, KEY)], client=FailingMidReportClient())

    with pytest.raises(DspDown):
        harness.service.run(DSP_ID, TODAY)


def test_every_batch_records_the_window_it_replaces_whether_it_succeeds_or_fails():
    harness = IngestionHarness(rows=[dsp_row(date(2026, 8, 5), KEY)], mapped_lines=[MappedLine(LINE, KEY)])
    harness.service.run(DSP_ID, TODAY)
    failing = IngestionHarness(client=FailingMidReportClient(), mapped_lines=[MappedLine(LINE, KEY)])
    with pytest.raises(DspDown):
        failing.service.run(DSP_ID, TODAY)

    expected = DeliveryDateRange(date(2026, 8, 3), date(2026, 8, 9))
    assert [b.window for b in harness.batches.records.values()] == [expected]
    assert [b.window for b in failing.batches.records.values()] == [expected]


def test_a_run_over_a_given_window_records_that_window_and_asks_for_it():
    window = DeliveryDateRange(date(2026, 7, 1), date(2026, 7, 20))
    harness = IngestionHarness(mapped_lines=[MappedLine(LINE, KEY)])

    harness.service.run(DSP_ID, TODAY, window=window)

    assert harness.client.requested_ranges == [window]
    assert next(iter(harness.batches.records.values())).window == window
