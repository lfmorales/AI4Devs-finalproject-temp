"""An active line without a validated mapping is skipped and reported; it never fails the run."""

from datetime import date

from app.domain.entities.ingestion_batch import BatchStatus
from app.domain.value_objects.delivery import ExternalLineKey
from app.domain.value_objects.ingestion import MappedLine
from tests.fixtures.delivery_rows import daily_delivery, dsp_row
from tests.fixtures.ingestion_harness import DSP_ID, IngestionHarness

TODAY = date(2026, 8, 10)
MAPPED = 11
UNMAPPED = 12
KEY = ExternalLineKey("100", "200")


def test_the_run_completes_for_every_mapped_line_when_another_line_is_unmapped():
    harness = IngestionHarness(rows=[dsp_row(date(2026, 8, 5), KEY, impressions=700)],
                               mapped_lines=[MappedLine(MAPPED, KEY)], unmapped_line_ids=[UNMAPPED])

    harness.service.run(DSP_ID, TODAY)

    assert harness.deliveries.impressions_by_line_and_day() == {(MAPPED, date(2026, 8, 5)): 700}
    assert next(iter(harness.batches.records.values())).status is BatchStatus.SUCCEEDED


def test_the_skipped_lines_are_reported():
    harness = IngestionHarness(mapped_lines=[MappedLine(MAPPED, KEY)], unmapped_line_ids=[UNMAPPED, 13])

    result = harness.service.run(DSP_ID, TODAY)

    assert result.skipped_line_ids == (UNMAPPED, 13)


def test_a_skipped_line_keeps_the_delivery_it_already_had():
    kept = daily_delivery(UNMAPPED, date(2026, 8, 5), impressions=555)
    harness = IngestionHarness(mapped_lines=[MappedLine(MAPPED, KEY)], unmapped_line_ids=[UNMAPPED], existing=[kept])

    harness.service.run(DSP_ID, TODAY)

    assert harness.deliveries.rows[(UNMAPPED, date(2026, 8, 5))] == kept


def test_a_run_where_no_line_is_mapped_still_succeeds_and_reports_them_all():
    harness = IngestionHarness(mapped_lines=[], unmapped_line_ids=[UNMAPPED])

    result = harness.service.run(DSP_ID, TODAY)

    assert (result.skipped_line_ids, harness.client.requested_ranges) == ((UNMAPPED,), [])
    assert next(iter(harness.batches.records.values())).status is BatchStatus.SUCCEEDED
