from dataclasses import replace
from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionType, IngestionException
from app.domain.entities.ingestion_batch import BatchStatus, IngestionBatch, IngestionRoute
from app.domain.repositories.ingestion_batch_repository import IngestionBatchRepository
from app.domain.repositories.ingestion_exception_repository import IngestionExceptionRepository
from app.domain.repositories.ingestion_target_repository import IngestionTargetRepository
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.value_objects.delivery import DeliveryDateRange, ExternalLineKey, RetainedDelivery
from app.domain.value_objects.ingestion import IngestionTargets
from collections.abc import Iterable
from datetime import date, datetime

from tests.fixtures.in_memory_delivery_repository import InMemoryDeliveryRepository


class InMemoryIngestionBatchRepository(IngestionBatchRepository):
    def __init__(self) -> None:
        self.records: dict[int, IngestionBatch] = {}

    def start(self, dsp_id: int, route: IngestionRoute, source_file: str | None, started_at: datetime) -> int:
        batch_id = len(self.records) + 1
        self.records[batch_id] = IngestionBatch(
            id=batch_id, dsp_id=dsp_id, route=route, source_file=source_file, started_at=started_at,
            finished_at=None, status=BatchStatus.RUNNING, row_count=0, ignored_row_count=0, zero_unmatched_row_count=0,
        )
        return batch_id

    def finish(
        self, batch_id: int, status: BatchStatus, finished_at: datetime, row_count: int, ignored_row_count: int,
        zero_unmatched_row_count: int,
    ) -> None:
        started = self.records[batch_id]
        self.records[batch_id] = IngestionBatch(
            id=batch_id, dsp_id=started.dsp_id, route=started.route, source_file=started.source_file,
            started_at=started.started_at, finished_at=finished_at, status=status,
            row_count=row_count, ignored_row_count=ignored_row_count,
            zero_unmatched_row_count=zero_unmatched_row_count,
        )


class InMemoryIngestionTargetRepository(IngestionTargetRepository):
    def __init__(self, targets: IngestionTargets, watched_campaign_ids: tuple[int, ...] = ()) -> None:
        self.targets = targets
        self.watched_campaign_ids = watched_campaign_ids
        self.requests: list[tuple[int, DeliveryDateRange]] = []

    def find_targets(self, dsp_id: int, window: DeliveryDateRange) -> IngestionTargets:
        self.requests.append((dsp_id, window))
        return self.targets

    def find_watched_campaign_ids(self, today: date) -> tuple[int, ...]:
        return self.watched_campaign_ids


class InMemoryIngestionExceptionRepository(IngestionExceptionRepository):
    def __init__(self) -> None:
        self.exceptions: dict[int, IngestionException] = {}
        self.retained: dict[tuple[int, date], RetainedDelivery] = {}

    def seed(self, exception: IngestionException) -> None:
        self.exceptions[exception.id] = exception

    def delete_retained_range(self, dsp_id: int, window: DeliveryDateRange) -> None:
        unmatched_of_dsp = {
            e.id for e in self.exceptions.values()
            if e.exception_type is ExceptionType.UNMATCHED_DELIVERY and e.dsp_id == dsp_id
        }
        self.retained = {
            (exception_id, day): row for (exception_id, day), row in self.retained.items()
            if not (exception_id in unmatched_of_dsp and window.contains(day))
        }

    def get_or_create_unmatched(self, dsp_id: int, key: ExternalLineKey, batch_id: int) -> int:
        for exception in self.exceptions.values():
            if (exception.exception_type is ExceptionType.UNMATCHED_DELIVERY and exception.dsp_id == dsp_id
                    and exception.key == key):
                return exception.id
        exception_id = max(self.exceptions, default=0) + 1
        self.exceptions[exception_id] = IngestionException(
            id=exception_id, exception_type=ExceptionType.UNMATCHED_DELIVERY, status=ExceptionStatus.OPEN,
            ingestion_batch_id=batch_id, dsp_id=dsp_id, key=key,
        )
        return exception_id

    def add_retained(self, exception_id: int, rows: Iterable[RetainedDelivery]) -> None:
        for row in rows:
            self.retained[(exception_id, row.delivery_date)] = row

    def refresh_unmatched_date_spans(self, dsp_id: int) -> None:
        for exception in list(self.exceptions.values()):
            if exception.exception_type is not ExceptionType.UNMATCHED_DELIVERY or exception.dsp_id != dsp_id:
                continue
            days = [day for (exception_id, day) in self.retained if exception_id == exception.id]
            if days:
                self.exceptions[exception.id] = replace(exception, first_date=min(days), last_date=max(days))


class InMemoryUnitOfWork(UnitOfWork):
    """Restores what it holds on rollback, the way a database transaction would."""

    def __init__(
        self,
        deliveries: InMemoryDeliveryRepository,
        batches: InMemoryIngestionBatchRepository | None = None,
        targets: InMemoryIngestionTargetRepository | None = None,
        exceptions: InMemoryIngestionExceptionRepository | None = None,
    ) -> None:
        self.deliveries = deliveries
        self.batches = batches or InMemoryIngestionBatchRepository()
        self.targets = targets or InMemoryIngestionTargetRepository(IngestionTargets(mapped_lines=()))
        self.exceptions = exceptions or InMemoryIngestionExceptionRepository()
        self.entered_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self._snapshot = dict(deliveries.rows)
        self._batch_snapshot = dict(self.batches.records)
        self._exception_snapshot = (dict(self.exceptions.exceptions), dict(self.exceptions.retained))

    def __enter__(self) -> "InMemoryUnitOfWork":
        self.entered_count += 1
        self._snapshot = dict(self.deliveries.rows)
        self._batch_snapshot = dict(self.batches.records)
        self._exception_snapshot = (dict(self.exceptions.exceptions), dict(self.exceptions.retained))
        return self

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1
        self.deliveries.rows = dict(self._snapshot)
        self.batches.records = dict(self._batch_snapshot)
        self.exceptions.exceptions, self.exceptions.retained = (
            dict(self._exception_snapshot[0]), dict(self._exception_snapshot[1]))
