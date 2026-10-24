from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.value_objects.delivery import DeliveryDateRange, ExternalLineKey


@dataclass(frozen=True)
class MappedLine:
    """A campaign line and the DSP identifiers its delivery arrives under."""

    campaign_line_id: int
    key: ExternalLineKey


@dataclass(frozen=True)
class IngestionTargets:
    """What a run ingests: the lines with a validated mapping, and the active lines it has to skip."""

    mapped_lines: tuple[MappedLine, ...]
    unmapped_line_ids: tuple[int, ...] = ()


def ingestion_window(today: date, window_days: int) -> DeliveryDateRange:
    """D-window_days to D-1: the rolling range every nightly run replaces."""
    if window_days < 1:
        raise ValueError("window_days must be at least 1")
    return DeliveryDateRange(start=today - timedelta(days=window_days), end=today - timedelta(days=1))
