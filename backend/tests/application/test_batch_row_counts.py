"""A batch counts the rows it read, and separately the rows it ignored and the unmatched rows of zeros."""

from datetime import date
from decimal import Decimal

from app.domain.value_objects.delivery import ExternalLineKey
from app.domain.value_objects.ingestion import MappedLine
from tests.fixtures.delivery_rows import dsp_row
from tests.fixtures.ingestion_harness import DSP_ID, IngestionHarness

TODAY = date(2026, 8, 10)
LINE = 11
KEY = ExternalLineKey("100", "200")
OTHER_KEY = ExternalLineKey("100", "201")
STRANGER = ExternalLineKey("9", "9")
DAY = date(2026, 8, 5)


def _mixed_rows():
    return [
        dsp_row(DAY, KEY, impressions=700),                                   # matched
        dsp_row(date(2026, 8, 6), KEY, impressions=0, media_cost=Decimal("0")),  # matched, zeros: still data
        dsp_row(DAY, OTHER_KEY, impressions=300),                             # matched, summed into the same line
        dsp_row(DAY, unattributed=True, impressions=50),                      # no attributed line item
        dsp_row(DAY, STRANGER, impressions=40),                               # unmatched, with impressions
        dsp_row(DAY, STRANGER, impressions=0, media_cost=Decimal("0.5")),     # unmatched, zero impressions but cost
        dsp_row(DAY, STRANGER, impressions=0, media_cost=Decimal("0")),       # unmatched, zeros
    ]


def _run():
    harness = IngestionHarness(rows=_mixed_rows(), mapped_lines=[MappedLine(LINE, KEY), MappedLine(LINE, OTHER_KEY)])
    result = harness.service.run(DSP_ID, TODAY)
    return harness, result, harness.batches.records[result.batch_id]


def test_row_count_is_the_number_of_rows_read():
    _, _, batch = _run()

    assert batch.row_count == 7


def test_rows_without_an_attributed_line_item_are_counted_as_ignored():
    _, _, batch = _run()

    assert batch.ignored_row_count == 1


def test_only_unmatched_rows_with_no_impressions_and_no_cost_are_counted_as_zero_unmatched():
    _, _, batch = _run()

    assert batch.zero_unmatched_row_count == 1


def test_the_result_reports_the_same_counts_and_what_was_stored():
    _, result, _ = _run()

    assert (result.rows_read, result.ignored_row_count, result.zero_unmatched_row_count) == (7, 1, 1)
    assert result.unmatched_row_count == 3
    assert result.stored_row_count == 2  # (line, Aug 5) summed from two line items, and (line, Aug 6)


def test_a_failed_run_records_no_counts():
    from tests.application.test_ingestion_batch_recording import DspDown, FailingMidReportClient
    import pytest

    harness = IngestionHarness(mapped_lines=[MappedLine(LINE, KEY)], client=FailingMidReportClient())

    with pytest.raises(DspDown):
        harness.service.run(DSP_ID, TODAY)

    batch = next(iter(harness.batches.records.values()))
    assert (batch.row_count, batch.ignored_row_count, batch.zero_unmatched_row_count) == (0, 0, 0)
