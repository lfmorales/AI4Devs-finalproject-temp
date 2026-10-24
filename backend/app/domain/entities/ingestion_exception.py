from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from app.domain.value_objects.delivery import ExternalLineKey


class ExceptionType(StrEnum):
    UNMATCHED_DELIVERY = "unmatched_delivery"
    MISSING_DELIVERY = "missing_delivery"
    # Defined but not generated: neither the statistics API nor the manual upload carries a line format.
    CHANNEL_MISMATCH = "channel_mismatch"


class ExceptionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class IngestionException:
    """Something an operations user has to work. Resolving it only marks it; nothing is reprocessed."""

    id: int
    exception_type: ExceptionType
    status: ExceptionStatus
    # The batch that first raised it.
    ingestion_batch_id: int
    dsp_id: int | None = None
    key: ExternalLineKey | None = None
    campaign_line_id: int | None = None
    campaign_period_id: int | None = None
    first_date: date | None = None
    last_date: date | None = None
    resolved_at: datetime | None = None
    resolved_by: int | None = None
    note: str | None = None


@dataclass(frozen=True)
class ExceptionSummary:
    """An exception as the queue shows it. Retained delivery is summarised, and its media cost is left out on purpose:
    cost is restricted to finance and the queue is open to operations."""

    id: int
    exception_type: ExceptionType
    status: ExceptionStatus
    ingestion_batch_id: int
    dsp_id: int | None = None
    external_campaign_id: str | None = None
    external_line_item_id: str | None = None
    campaign_line_id: int | None = None
    campaign_period_id: int | None = None
    first_date: date | None = None
    last_date: date | None = None
    days: int = 0
    impressions_total: int = 0
    clicks_total: int = 0
    resolved_at: datetime | None = None
    resolved_by: int | None = None
    note: str | None = None
