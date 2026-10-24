from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime

from app.domain.entities.ingestion_batch import BatchStatus, IngestionRoute
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.services.delivery_combination import combine_daily_deliveries
from app.domain.services.delivery_range_replacement import DeliveryRangeReplacer
from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey
from app.domain.value_objects.ingestion import IngestionTargets, ingestion_window

DEFAULT_WINDOW_DAYS = 7


@dataclass(frozen=True)
class IngestionRunResult:
    batch_id: int
    window: DeliveryDateRange
    stored_row_count: int
    unmatched_row_count: int
    skipped_line_ids: tuple[int, ...] = ()


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
            stored_row_count, unmatched_row_count = self._ingest(batch_id, window, targets)
        except Exception:
            # The range already rolled back whole; the failed batch is what tells operations the run happened.
            self._finish_batch(batch_id, BatchStatus.FAILED, row_count=0)
            raise
        self._finish_batch(batch_id, BatchStatus.SUCCEEDED, stored_row_count)
        return IngestionRunResult(batch_id, window, stored_row_count, unmatched_row_count, targets.unmapped_line_ids)

    def _start_batch(self, dsp_id: int, route: IngestionRoute, source_file: str | None) -> int:
        # Its own transaction, committed before the data one, so the batch exists whatever happens next.
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.batches.start(dsp_id, route, source_file, self._clock())

    def _find_targets(self, dsp_id: int, window: DeliveryDateRange) -> IngestionTargets:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.targets.find_targets(dsp_id, window)

    def _ingest(self, batch_id: int, window: DeliveryDateRange, targets: IngestionTargets) -> tuple[int, int]:
        if not targets.mapped_lines:
            return 0, 0  # Nothing to ask the DSP for; the quota is shared with the whole agency.

        line_by_key = {
            ExternalLineKey.from_raw(line.key.external_campaign_id, line.key.external_line_item_id): line.campaign_line_id
            for line in targets.mapped_lines
        }
        unmatched_row_count = 0

        def _attributed_rows() -> Iterator[tuple[int, DspDeliveryRow]]:
            nonlocal unmatched_row_count
            for row in self._dsp_client.fetch_delivery(window):
                campaign_line_id = line_by_key.get(ExternalLineKey.from_raw(row.key.external_campaign_id,
                                                                            row.key.external_line_item_id))
                if campaign_line_id is None:
                    unmatched_row_count += 1
                    continue
                yield campaign_line_id, row

        # The DSP is read before any transaction opens, so a slow report never holds the database.
        deliveries = combine_daily_deliveries(_attributed_rows(), batch_id)
        with self._unit_of_work_factory() as unit_of_work:
            stored = DeliveryRangeReplacer(unit_of_work).replace_range(
                {line.campaign_line_id for line in targets.mapped_lines}, window, deliveries
            )
        return stored, unmatched_row_count

    def _finish_batch(self, batch_id: int, status: BatchStatus, row_count: int) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.batches.finish(batch_id, status, self._clock(), row_count, ignored_row_count=0)
