from collections.abc import Callable
from types import TracebackType

from sqlalchemy.orm import Session

from app.domain.repositories.unit_of_work import UnitOfWork
from app.infrastructure.persistence.repositories.sqlalchemy_delivery_repository import (
    SqlAlchemyDeliveryRepository,
    SqlAlchemyIngestionBatchRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_ingestion_exception_repository import (
    SqlAlchemyIngestionExceptionRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_ingestion_target_repository import (
    SqlAlchemyIngestionTargetRepository,
)


class SqlAlchemyUnitOfWork(UnitOfWork):
    """One database transaction: its repositories share a session that commits or rolls back as a whole."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        session = self._session_factory()
        self._session = session
        self.deliveries = SqlAlchemyDeliveryRepository(session)
        self.batches = SqlAlchemyIngestionBatchRepository(session)
        self.targets = SqlAlchemyIngestionTargetRepository(session)
        self.exceptions = SqlAlchemyIngestionExceptionRepository(session)
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            super().__exit__(exception_type, exception, traceback)
        finally:
            assert self._session is not None
            self._session.close()

    def commit(self) -> None:
        assert self._session is not None
        self._session.commit()

    def rollback(self) -> None:
        assert self._session is not None
        self._session.rollback()
