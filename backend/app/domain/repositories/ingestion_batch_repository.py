from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.entities.ingestion_batch import BatchStatus, IngestionRoute
from app.domain.value_objects.delivery import DeliveryDateRange


class IngestionBatchRepository(ABC):
    @abstractmethod
    def start(
        self, dsp_id: int, route: IngestionRoute, source_file: str | None, started_at: datetime,
        window: DeliveryDateRange,
    ) -> int:
        """Record a run and the window it replaces as running and return the id its deliveries will reference."""

    @abstractmethod
    def finish(
        self,
        batch_id: int,
        status: BatchStatus,
        finished_at: datetime,
        row_count: int,
        ignored_row_count: int,
        zero_unmatched_row_count: int,
    ) -> None:
        """Record how the run ended: rows read, rows ignored for having no line item, unmatched rows of zeros."""
