from collections.abc import Callable
from datetime import datetime

from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionSummary
from app.domain.exceptions import IngestionExceptionAlreadyResolvedError, IngestionExceptionNotFoundError
from app.domain.repositories.exception_queue_repository import ExceptionQueueRepository


class IngestionExceptionService:
    def __init__(self, queue: ExceptionQueueRepository, clock: Callable[[], datetime]) -> None:
        self._queue = queue
        self._clock = clock

    def list_exceptions(self, status: ExceptionStatus | None) -> list[ExceptionSummary]:
        return self._queue.list_summaries(status)

    def resolve(self, exception_id: int, resolved_by: int, note: str | None) -> ExceptionSummary:
        """Mark an exception resolved. Only marks: nothing is reprocessed and retained delivery stays where it is."""
        summary = self._queue.get_summary(exception_id)
        if summary is None:
            raise IngestionExceptionNotFoundError(f"exception {exception_id} does not exist")
        if summary.status is ExceptionStatus.RESOLVED:
            raise IngestionExceptionAlreadyResolvedError(f"exception {exception_id} is already resolved")
        # The conditional update decides when two requests resolve the same exception at once.
        if not self._queue.mark_resolved(exception_id, self._clock(), resolved_by, note):
            raise IngestionExceptionAlreadyResolvedError(f"exception {exception_id} is already resolved")
        resolved = self._queue.get_summary(exception_id)
        assert resolved is not None
        return resolved
