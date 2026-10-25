from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.domain.repositories.delivery_repository import DeliveryRepository
from app.domain.repositories.dsp_catalog_repository import DspCatalogRepository
from app.domain.repositories.ingestion_batch_repository import IngestionBatchRepository
from app.domain.repositories.ingestion_exception_repository import IngestionExceptionRepository
from app.domain.repositories.ingestion_target_repository import IngestionTargetRepository


class UnitOfWork(ABC):
    """The transactional boundary of an ingestion run: what happens inside the block lands whole or not at all.

    The domain states the boundary; infrastructure decides what a transaction is.
    """

    deliveries: DeliveryRepository
    batches: IngestionBatchRepository
    targets: IngestionTargetRepository
    exceptions: IngestionExceptionRepository
    catalog: DspCatalogRepository

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # Returns None so the original failure keeps propagating after the rollback.
        if exception_type is None:
            self.commit()
        else:
            self.rollback()

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...
