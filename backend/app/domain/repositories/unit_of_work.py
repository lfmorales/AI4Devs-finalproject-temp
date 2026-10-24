from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.domain.repositories.delivery_repository import DeliveryRepository


class UnitOfWork(ABC):
    """The transactional boundary of an ingestion run: what happens inside the block lands whole or not at all.

    The domain states the boundary; infrastructure decides what a transaction is.
    """

    deliveries: DeliveryRepository

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
