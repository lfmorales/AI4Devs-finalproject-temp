"""Delivery the DSP does not attribute to a line item is counted on the batch; other currencies fail the run."""

from collections.abc import Iterator
from datetime import date

import pytest

from app.domain.entities.ingestion_batch import BatchStatus
from app.domain.exceptions import UnsupportedCurrencyError
from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey
from app.domain.value_objects.ingestion import MappedLine
from tests.fixtures.delivery_rows import daily_delivery, dsp_row
from tests.fixtures.ingestion_harness import DSP_ID, IngestionHarness

TODAY = date(2026, 8, 10)
LINE = 11
KEY = ExternalLineKey("100", "200")


class ClientReportingForeignCurrency(DspDeliveryClient):
    def fetch_delivery(self, date_range: DeliveryDateRange) -> Iterator[DspDeliveryRow]:
        yield dsp_row(date(2026, 8, 5), KEY)
        raise UnsupportedCurrencyError("GBP")

    def resolve_identifiers(self, external_campaign_id: str, external_line_item_id: str) -> ExternalLineKey | None:
        return None


def _rows_with_two_unattributed():
    return [
        dsp_row(date(2026, 8, 5), KEY, impressions=700),
        dsp_row(date(2026, 8, 5), unattributed=True, impressions=50),
        dsp_row(date(2026, 8, 6), unattributed=True, impressions=60),
    ]


def test_unattributed_rows_are_counted_on_the_batch_and_the_result():
    harness = IngestionHarness(rows=_rows_with_two_unattributed(), mapped_lines=[MappedLine(LINE, KEY)])

    result = harness.service.run(DSP_ID, TODAY)

    batch = harness.batches.records[result.batch_id]
    assert (result.ignored_row_count, batch.ignored_row_count) == (2, 2)


def test_unattributed_rows_are_not_stored():
    harness = IngestionHarness(rows=_rows_with_two_unattributed(), mapped_lines=[MappedLine(LINE, KEY)])

    harness.service.run(DSP_ID, TODAY)

    assert harness.deliveries.impressions_by_line_and_day() == {(LINE, date(2026, 8, 5)): 700}


def test_unattributed_rows_are_ignored_not_unmatched():
    harness = IngestionHarness(rows=_rows_with_two_unattributed(), mapped_lines=[MappedLine(LINE, KEY)])

    result = harness.service.run(DSP_ID, TODAY)

    assert result.unmatched_row_count == 0


def test_a_currency_other_than_eur_fails_the_batch_and_stores_nothing():
    previous = daily_delivery(LINE, date(2026, 8, 5), impressions=1000)
    harness = IngestionHarness(mapped_lines=[MappedLine(LINE, KEY)], existing=[previous],
                               client=ClientReportingForeignCurrency())

    with pytest.raises(UnsupportedCurrencyError):
        harness.service.run(DSP_ID, TODAY)

    assert next(iter(harness.batches.records.values())).status is BatchStatus.FAILED
    assert harness.deliveries.rows == {(LINE, date(2026, 8, 5)): previous}
