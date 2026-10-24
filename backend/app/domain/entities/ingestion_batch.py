from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class IngestionRoute(StrEnum):
    API = "api"
    UPLOAD = "upload"
    EMAIL = "email"


class BatchStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class IngestionBatch:
    """One ingestion run, whatever route it arrived by."""

    id: int
    dsp_id: int
    route: IngestionRoute
    source_file: str | None
    started_at: datetime
    finished_at: datetime | None
    status: BatchStatus
    row_count: int
    ignored_row_count: int
