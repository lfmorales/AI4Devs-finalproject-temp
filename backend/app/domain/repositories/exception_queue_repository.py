from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionSummary


class ExceptionQueueRepository(ABC):
    """Reads the exception queue and marks exceptions resolved. Reprocessing is not part of resolving."""

    @abstractmethod
    def list_summaries(self, status: ExceptionStatus | None) -> list[ExceptionSummary]:
        """The exceptions with that status, or all of them, ordered by id."""

    @abstractmethod
    def get_summary(self, exception_id: int) -> ExceptionSummary | None: ...

    @abstractmethod
    def mark_resolved(self, exception_id: int, resolved_at: datetime, resolved_by: int, note: str | None) -> bool:
        """Mark an open exception resolved. False when it was not open, so a resolution is never overwritten."""
