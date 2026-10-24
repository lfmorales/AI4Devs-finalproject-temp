"""Memory follows the number of line-and-day pairs in the window, not the number of rows the DSP reports."""

import tracemalloc
from collections.abc import Iterable, Iterator
from datetime import date, timedelta

from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.value_objects.delivery import DailyDelivery, DeliveryDateRange, DspDeliveryRow, ExternalLineKey
from app.domain.value_objects.ingestion import MappedLine
from tests.fixtures.delivery_rows import dsp_row
from tests.fixtures.in_memory_delivery_repository import InMemoryDeliveryRepository
from tests.fixtures.ingestion_harness import DSP_ID, IngestionHarness

TODAY = date(2026, 8, 10)
TOTAL_ROWS = 1_000_000
LINES = 40
PEAK_MEMORY_BUDGET_BYTES = 5 * 1024 * 1024  # Streamed: ~0.1 MB. Just 200,000 materialised rows already take ~30 MB.


class MillionRowClient(DspDeliveryClient):
    """Generates rows on demand; spread over 40 lines x 7 days, so combining collapses them to 280 records."""

    def __init__(self) -> None:
        self._keys = [ExternalLineKey(str(line), "1") for line in range(LINES)]
        self.rows_produced = 0

    def fetch_delivery(self, date_range: DeliveryDateRange) -> Iterator[DspDeliveryRow]:
        days = date_range.days()
        for index in range(TOTAL_ROWS):
            self.rows_produced += 1
            yield dsp_row(days[index % len(days)], self._keys[index % LINES])

    def resolve_identifiers(self, external_campaign_id: str, external_line_item_id: str) -> ExternalLineKey | None:
        return None


class CountingRepository(InMemoryDeliveryRepository):
    """Counts what it is given without keeping it, to measure the service rather than the test double."""

    stored = 0

    def add_all(self, deliveries: Iterable[DailyDelivery]) -> None:
        for _ in deliveries:
            self.stored += 1


def test_a_million_row_run_stays_within_a_bounded_amount_of_memory():
    client = MillionRowClient()
    harness = IngestionHarness(
        mapped_lines=[MappedLine(line, ExternalLineKey(str(line), "1")) for line in range(LINES)], client=client
    )
    harness.deliveries = CountingRepository()

    tracemalloc.start()
    try:
        result = harness.service.run(DSP_ID, TODAY)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert client.rows_produced == TOTAL_ROWS
    assert harness.deliveries.stored == LINES * 7 == result.stored_row_count
    assert peak < PEAK_MEMORY_BUDGET_BYTES
