"""The ingestion fills the DSP line catalogue from every attributed row of the window, in the batch's transaction."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.entities.ingestion_batch import BatchStatus
from app.domain.value_objects.catalog import CatalogLineObservation
from app.domain.value_objects.delivery import ExternalLineKey
from app.domain.value_objects.ingestion import MappedLine
from tests.fixtures.delivery_rows import catalog_info, dsp_row
from tests.fixtures.dsp_delivery_client import InMemoryDspDeliveryClient
from tests.fixtures.ingestion_harness import DSP_ID, IngestionHarness

TODAY = date(2026, 8, 10)
KEY = ExternalLineKey("100", "200")
OTHER_KEY = ExternalLineKey("100", "201")


def _row(day: int, key: ExternalLineKey = KEY, impressions: int = 500, name: str = "Synthetic Line", **kwargs):
    return dsp_row(date(2026, 8, day), key, impressions=impressions, catalog=catalog_info(line_item_name=name), **kwargs)


def _entry(harness: IngestionHarness, key: ExternalLineKey = KEY) -> CatalogLineObservation:
    return harness.catalog.entries[(DSP_ID, key)]


def test_a_new_pair_enters_with_its_names_dates_and_seen_dates():
    harness = IngestionHarness(rows=[_row(4), _row(6)], mapped_lines=[MappedLine(11, KEY)])

    harness.service.run(DSP_ID, TODAY)

    assert _entry(harness) == CatalogLineObservation(
        key=KEY, campaign_name="Synthetic Campaign", line_item_name="Synthetic Line",
        line_start_date=date(2026, 7, 1), line_end_date=date(2026, 9, 30),
        first_seen_date=date(2026, 8, 4), last_seen_date=date(2026, 8, 6), last_impressions_date=date(2026, 8, 6),
    )


def test_a_pair_that_is_not_mapped_enters_too():
    harness = IngestionHarness(rows=[_row(5, OTHER_KEY)], mapped_lines=[MappedLine(11, KEY)])

    harness.service.run(DSP_ID, TODAY)

    assert set(key for _, key in harness.catalog.entries) == {OTHER_KEY}


def test_a_pair_that_only_delivers_zeros_enters_without_an_impressions_date():
    harness = IngestionHarness(rows=[_row(4, impressions=0, media_cost=Decimal("0")), _row(5, impressions=0)])

    harness.service.run(DSP_ID, TODAY)

    entry = _entry(harness)
    assert (entry.first_seen_date, entry.last_seen_date, entry.last_impressions_date) == (
        date(2026, 8, 4), date(2026, 8, 5), None)


def test_the_impressions_date_is_the_latest_date_with_impressions_not_the_latest_row():
    harness = IngestionHarness(rows=[_row(4, impressions=10), _row(6, impressions=20), _row(8, impressions=0)])

    harness.service.run(DSP_ID, TODAY)

    entry = _entry(harness)
    assert (entry.last_seen_date, entry.last_impressions_date) == (date(2026, 8, 8), date(2026, 8, 6))


def test_rows_without_an_attributed_line_do_not_enter():
    harness = IngestionHarness(rows=[dsp_row(date(2026, 8, 5), unattributed=True)])

    harness.service.run(DSP_ID, TODAY)

    assert harness.catalog.entries == {}


def test_rows_without_catalogue_information_do_not_enter():
    harness = IngestionHarness(rows=[dsp_row(date(2026, 8, 5), KEY)])

    harness.service.run(DSP_ID, TODAY)

    assert harness.catalog.entries == {}


def test_the_names_and_dates_come_from_the_latest_row_of_the_pair():
    harness = IngestionHarness(rows=[_row(4, name="Old name"), _row(7, name="New name"), _row(5, name="Middle name")])

    harness.service.run(DSP_ID, TODAY)

    assert _entry(harness).line_item_name == "New name"


def test_a_later_run_updates_the_names_and_only_widens_the_seen_dates():
    harness = IngestionHarness(rows=[_row(4, name="First name")])
    harness.service.run(DSP_ID, TODAY)
    harness.client = InMemoryDspDeliveryClient([_row(8, name="Renamed")])
    harness.service._dsp_client = harness.client

    harness.service.run(DSP_ID, TODAY)

    entry = _entry(harness)
    assert (entry.line_item_name, entry.first_seen_date, entry.last_seen_date) == ("Renamed", date(2026, 8, 4), date(2026, 8, 8))


def test_an_older_range_widens_the_dates_but_does_not_overwrite_the_names():
    harness = IngestionHarness(rows=[_row(8, name="Current name")])
    harness.service.run(DSP_ID, TODAY)
    harness.service._dsp_client = InMemoryDspDeliveryClient([_row(4, name="Stale name")])

    harness.service.run(DSP_ID, TODAY)

    entry = _entry(harness)
    assert (entry.line_item_name, entry.first_seen_date, entry.last_seen_date) == ("Current name", date(2026, 8, 4), date(2026, 8, 8))


def test_repeating_a_run_changes_nothing():
    harness = IngestionHarness(rows=[_row(4), _row(6)])
    harness.service.run(DSP_ID, TODAY)
    first = dict(harness.catalog.entries)

    harness.service.run(DSP_ID, TODAY)

    assert harness.catalog.entries == first


def test_a_run_with_no_mapped_line_still_asks_the_dsp_once_and_fills_the_catalogue():
    harness = IngestionHarness(rows=[_row(5)], mapped_lines=[])

    result = harness.service.run(DSP_ID, TODAY)

    assert len(harness.client.requested_ranges) == 1
    assert set(key for _, key in harness.catalog.entries) == {KEY}
    assert (result.mapped_line_count, next(iter(harness.batches.records.values())).status) == (0, BatchStatus.SUCCEEDED)


def test_the_result_counts_the_mapped_lines():
    harness = IngestionHarness(mapped_lines=[MappedLine(11, KEY), MappedLine(11, OTHER_KEY), MappedLine(12, ExternalLineKey("1", "2"))])

    assert harness.service.run(DSP_ID, TODAY).mapped_line_count == 2


class _FailingAfterTheCatalogue(InMemoryDspDeliveryClient):
    """Serves its rows, then fails: the delivery stream breaks before the run can finish."""

    def fetch_delivery(self, date_range):
        yield from super().fetch_delivery(date_range)
        raise RuntimeError("the report broke")


def test_a_failed_batch_leaves_the_catalogue_as_it_was():
    harness = IngestionHarness(rows=[_row(4, name="Before")])
    harness.service.run(DSP_ID, TODAY)
    before = dict(harness.catalog.entries)
    harness.service._dsp_client = _FailingAfterTheCatalogue([_row(8, name="After")])

    with pytest.raises(RuntimeError):
        harness.service.run(DSP_ID, TODAY)

    assert harness.catalog.entries == before
    assert [b.status for b in harness.batches.records.values()] == [BatchStatus.SUCCEEDED, BatchStatus.FAILED]


def test_a_failure_after_the_catalogue_was_written_rolls_it_back():
    harness = IngestionHarness(rows=[_row(5, OTHER_KEY)], mapped_lines=[MappedLine(11, KEY)])

    def explode(*_args, **_kwargs):
        raise RuntimeError("the exception store failed")

    harness.exceptions.get_or_create_unmatched = explode  # runs after the catalogue write, in the same transaction

    with pytest.raises(RuntimeError):
        harness.service.run(DSP_ID, TODAY)

    assert harness.catalog.entries == {}
