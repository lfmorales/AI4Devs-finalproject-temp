from dataclasses import replace
from datetime import datetime

from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionSummary
from app.domain.repositories.exception_queue_repository import ExceptionQueueRepository


class InMemoryExceptionQueueRepository(ExceptionQueueRepository):
    def __init__(self, summaries: list[ExceptionSummary]) -> None:
        self.summaries = {summary.id: summary for summary in summaries}

    def list_summaries(self, status: ExceptionStatus | None) -> list[ExceptionSummary]:
        return sorted((s for s in self.summaries.values() if status is None or s.status is status), key=lambda s: s.id)

    def get_summary(self, exception_id: int) -> ExceptionSummary | None:
        return self.summaries.get(exception_id)

    def mark_resolved(self, exception_id: int, resolved_at: datetime, resolved_by: int, note: str | None) -> bool:
        summary = self.summaries[exception_id]
        if summary.status is not ExceptionStatus.OPEN:
            return False
        self.summaries[exception_id] = replace(
            summary, status=ExceptionStatus.RESOLVED, resolved_at=resolved_at, resolved_by=resolved_by, note=note)
        return True
