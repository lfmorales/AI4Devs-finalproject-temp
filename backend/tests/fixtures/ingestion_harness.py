"""Wires the ingestion service to in-memory doubles and exposes what the tests assert on."""

from collections.abc import Callable, Iterable
from datetime import datetime

from app.application.services.delivery_ingestion_service import DeliveryIngestionService
from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.value_objects.delivery import DailyDelivery, DspDeliveryRow
from app.domain.value_objects.ingestion import IngestionTargets, MappedLine
from tests.fixtures.dsp_delivery_client import InMemoryDspDeliveryClient
from tests.fixtures.in_memory_delivery_repository import InMemoryDeliveryRepository
from tests.fixtures.in_memory_unit_of_work import (
    InMemoryIngestionBatchRepository,
    InMemoryIngestionExceptionRepository,
    InMemoryIngestionTargetRepository,
    InMemoryUnitOfWork,
)

DSP_ID = 1
NOW = datetime(2026, 8, 10, 2, 0)


class IngestionHarness:
    def __init__(
        self,
        rows: Iterable[DspDeliveryRow] = (),
        mapped_lines: Iterable[MappedLine] = (),
        unmapped_line_ids: Iterable[int] = (),
        existing: Iterable[DailyDelivery] = (),
        window_days: int = 7,
        client: DspDeliveryClient | None = None,
    ) -> None:
        self.client = client or InMemoryDspDeliveryClient(rows)
        self.deliveries = InMemoryDeliveryRepository(existing)
        self.batches = InMemoryIngestionBatchRepository()
        self.exceptions = InMemoryIngestionExceptionRepository()
        self.targets = InMemoryIngestionTargetRepository(
            IngestionTargets(mapped_lines=tuple(mapped_lines), unmapped_line_ids=tuple(unmapped_line_ids))
        )
        self.units_of_work: list[InMemoryUnitOfWork] = []
        self.service = DeliveryIngestionService(
            dsp_client=self.client,
            unit_of_work_factory=self._new_unit_of_work,
            clock=lambda: NOW,
            window_days=window_days,
        )

    def _new_unit_of_work(self) -> InMemoryUnitOfWork:
        unit_of_work = InMemoryUnitOfWork(self.deliveries, self.batches, self.targets, self.exceptions)
        self.units_of_work.append(unit_of_work)
        return unit_of_work


UnitOfWorkFactory = Callable[[], InMemoryUnitOfWork]
