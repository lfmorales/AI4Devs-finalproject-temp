from app.domain.entities.ingestion_batch import BatchStatus, IngestionBatch, IngestionRoute
from app.domain.repositories.ingestion_batch_repository import IngestionBatchRepository
from app.domain.repositories.ingestion_target_repository import IngestionTargetRepository
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.value_objects.delivery import DeliveryDateRange
from app.domain.value_objects.ingestion import IngestionTargets
from datetime import datetime

from tests.fixtures.in_memory_delivery_repository import InMemoryDeliveryRepository


class InMemoryIngestionBatchRepository(IngestionBatchRepository):
    def __init__(self) -> None:
        self.records: dict[int, IngestionBatch] = {}

    def start(self, dsp_id: int, route: IngestionRoute, source_file: str | None, started_at: datetime) -> int:
        batch_id = len(self.records) + 1
        self.records[batch_id] = IngestionBatch(
            id=batch_id, dsp_id=dsp_id, route=route, source_file=source_file, started_at=started_at,
            finished_at=None, status=BatchStatus.RUNNING, row_count=0, ignored_row_count=0,
        )
        return batch_id

    def finish(
        self, batch_id: int, status: BatchStatus, finished_at: datetime, row_count: int, ignored_row_count: int
    ) -> None:
        started = self.records[batch_id]
        self.records[batch_id] = IngestionBatch(
            id=batch_id, dsp_id=started.dsp_id, route=started.route, source_file=started.source_file,
            started_at=started.started_at, finished_at=finished_at, status=status,
            row_count=row_count, ignored_row_count=ignored_row_count,
        )


class InMemoryIngestionTargetRepository(IngestionTargetRepository):
    def __init__(self, targets: IngestionTargets) -> None:
        self.targets = targets
        self.requests: list[tuple[int, DeliveryDateRange]] = []

    def find_targets(self, dsp_id: int, window: DeliveryDateRange) -> IngestionTargets:
        self.requests.append((dsp_id, window))
        return self.targets


class InMemoryUnitOfWork(UnitOfWork):
    """Restores what it holds on rollback, the way a database transaction would."""

    def __init__(
        self,
        deliveries: InMemoryDeliveryRepository,
        batches: InMemoryIngestionBatchRepository | None = None,
        targets: InMemoryIngestionTargetRepository | None = None,
    ) -> None:
        self.deliveries = deliveries
        self.batches = batches or InMemoryIngestionBatchRepository()
        self.targets = targets or InMemoryIngestionTargetRepository(IngestionTargets(mapped_lines=()))
        self.entered_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self._snapshot = dict(deliveries.rows)
        self._batch_snapshot = dict(self.batches.records)

    def __enter__(self) -> "InMemoryUnitOfWork":
        self.entered_count += 1
        self._snapshot = dict(self.deliveries.rows)
        self._batch_snapshot = dict(self.batches.records)
        return self

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1
        self.deliveries.rows = dict(self._snapshot)
        self.batches.records = dict(self._batch_snapshot)
