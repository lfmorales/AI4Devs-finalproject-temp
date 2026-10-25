from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime

from app.domain.entities.ingestion_batch import BatchStatus, IngestionRoute
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.services.catalog_observation import CatalogObserver
from app.domain.services.delivery_combination import combine_daily_deliveries
from app.domain.services.delivery_range_replacement import DeliveryRangeReplacer
from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.services.unmatched_delivery_recording import (
    UnmatchedDeliveryRecorder,
    has_something_to_work,
    retain,
)
from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey, RetainedDelivery
from app.domain.value_objects.ingestion import IngestionTargets, ingestion_window

DEFAULT_WINDOW_DAYS = 7


@dataclass(frozen=True)
class _RunCounts:
    rows_read: int = 0
    stored_row_count: int = 0
    unmatched_row_count: int = 0
    ignored_row_count: int = 0
    zero_unmatched_row_count: int = 0


@dataclass(frozen=True)
class IngestionRunResult:
    batch_id: int
    window: DeliveryDateRange
    rows_read: int
    stored_row_count: int
    # Every unmatched row, including the zero ones that are counted but not worked.
    unmatched_row_count: int
    ignored_row_count: int
    zero_unmatched_row_count: int
    skipped_line_ids: tuple[int, ...] = ()
    mapped_line_count: int = 0


class DeliveryIngestionService:
    """Ingests a DSP's delivery for the rolling window, replacing what the window already held."""

    def __init__(
        self,
        dsp_client: DspDeliveryClient,
        unit_of_work_factory: Callable[[], UnitOfWork],
        clock: Callable[[], datetime],
        window_days: int = DEFAULT_WINDOW_DAYS,
    ) -> None:
        self._dsp_client = dsp_client
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._window_days = window_days

    def run(
        self,
        dsp_id: int,
        today: date,
        route: IngestionRoute = IngestionRoute.API,
        source_file: str | None = None,
    ) -> IngestionRunResult:
        window = ingestion_window(today, self._window_days)
        batch_id = self._start_batch(dsp_id, route, source_file)
        try:
            targets = self._find_targets(dsp_id, window)
            counts = self._ingest(dsp_id, batch_id, window, targets)
        except Exception:
            # The range already rolled back whole; the failed batch is what tells operations the run happened.
            self._finish_batch(batch_id, BatchStatus.FAILED, _RunCounts())
            raise
        self._finish_batch(batch_id, BatchStatus.SUCCEEDED, counts)
        return IngestionRunResult(
            batch_id, window, counts.rows_read, counts.stored_row_count, counts.unmatched_row_count,
            counts.ignored_row_count, counts.zero_unmatched_row_count, targets.unmapped_line_ids,
            len({line.campaign_line_id for line in targets.mapped_lines}),
        )

    def detect_missing_delivery(self, dsp_id: int, today: date, batch_id: int) -> int:
        """Record an exception for every mapped line with no impressions in a period that ended inside the window.

        Not wired to any scheduler. Safe to repeat: a line and period have at most one exception.
        Returns how many exceptions were new.
        """
        window = ingestion_window(today, self._window_days)
        with self._unit_of_work_factory() as unit_of_work:
            candidates = unit_of_work.targets.find_lines_missing_delivery(dsp_id, window)
            return sum(
                unit_of_work.exceptions.record_missing_delivery(
                    candidate.campaign_line_id, candidate.campaign_period_id, batch_id
                )
                for candidate in candidates
            )

    def _start_batch(self, dsp_id: int, route: IngestionRoute, source_file: str | None) -> int:
        # Its own transaction, committed before the data one, so the batch exists whatever happens next.
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.batches.start(dsp_id, route, source_file, self._clock())

    def _find_targets(self, dsp_id: int, window: DeliveryDateRange) -> IngestionTargets:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.targets.find_targets(dsp_id, window)

    def _ingest(
        self, dsp_id: int, batch_id: int, window: DeliveryDateRange, targets: IngestionTargets
    ) -> _RunCounts:
        # The DSP is asked even when no line is mapped: the catalogue has to be filled before the first mapping.
        line_by_key = {
            ExternalLineKey.from_raw(line.key.external_campaign_id, line.key.external_line_item_id): line.campaign_line_id
            for line in targets.mapped_lines
        }
        rows_read = unmatched_row_count = ignored_row_count = zero_unmatched_row_count = 0
        retained: dict[tuple[ExternalLineKey, date], RetainedDelivery] = {}
        catalog = CatalogObserver()

        def _attributed_rows() -> Iterator[tuple[int, DspDeliveryRow]]:
            nonlocal rows_read, unmatched_row_count, ignored_row_count, zero_unmatched_row_count
            for row in self._dsp_client.fetch_delivery(window):
                rows_read += 1
                catalog.add(row)  # every attributed row of the window, mapped or not, zeros or not
                if row.key is None:
                    # Counted on the batch, never worked as an exception: there is no line item to chase.
                    ignored_row_count += 1
                    continue
                campaign_line_id = line_by_key.get(
                    ExternalLineKey.from_raw(row.key.external_campaign_id, row.key.external_line_item_id)
                )
                if campaign_line_id is None:
                    unmatched_row_count += 1
                    if has_something_to_work(row):
                        key = ExternalLineKey.from_raw(row.key.external_campaign_id, row.key.external_line_item_id)
                        retained[(key, row.delivery_date)] = retain(retained.get((key, row.delivery_date)), key, row)
                    else:
                        # The statistics API returns many rows of zeros for active campaigns; counted, not worked.
                        zero_unmatched_row_count += 1
                    continue
                yield campaign_line_id, row

        # The DSP is read before any transaction opens, so a slow report never holds the database.
        deliveries = combine_daily_deliveries(_attributed_rows(), batch_id)
        # Deliveries and exceptions share one transaction: a run lands whole or not at all.
        with self._unit_of_work_factory() as unit_of_work:
            stored = DeliveryRangeReplacer(unit_of_work).replace_range_in_transaction(
                {line.campaign_line_id for line in targets.mapped_lines}, window, deliveries
            )
            # After the stream above has been consumed, before the exceptions: all in this one transaction.
            unit_of_work.catalog.upsert_all(dsp_id, catalog.observations())
            UnmatchedDeliveryRecorder().record(
                unit_of_work.exceptions, dsp_id, batch_id, window, retained.values()
            )
        return _RunCounts(rows_read, stored, unmatched_row_count, ignored_row_count, zero_unmatched_row_count)

    def _finish_batch(self, batch_id: int, status: BatchStatus, counts: _RunCounts) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.batches.finish(
                batch_id, status, self._clock(), counts.rows_read, counts.ignored_row_count,
                counts.zero_unmatched_row_count,
            )
