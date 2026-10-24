from types import TracebackType

from app.domain.repositories.unit_of_work import UnitOfWork
from tests.fixtures.in_memory_delivery_repository import InMemoryDeliveryRepository


class InMemoryUnitOfWork(UnitOfWork):
    """Restores the repository's rows on rollback, the way a database transaction would."""

    def __init__(self, deliveries: InMemoryDeliveryRepository) -> None:
        self.deliveries = deliveries
        self.entered_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self._snapshot = dict(deliveries.rows)

    def __enter__(self) -> "InMemoryUnitOfWork":
        self.entered_count += 1
        self._snapshot = dict(self.deliveries.rows)
        return self

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1
        self.deliveries.rows = dict(self._snapshot)
