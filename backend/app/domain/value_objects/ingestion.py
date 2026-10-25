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


@dataclass(frozen=True)
class MissingDeliveryCandidate:
    """A mapped line and a finished period in which it delivered nothing."""

    campaign_line_id: int
    campaign_period_id: int


def ingestion_window(today: date, window_days: int) -> DeliveryDateRange:
    """D-window_days to D-1: the rolling range every nightly run replaces."""
    if window_days < 1:
        raise ValueError("window_days must be at least 1")
    return DeliveryDateRange(start=today - timedelta(days=window_days), end=today - timedelta(days=1))


def needs_history_load(line_start: date, today: date, window_days: int = 7) -> bool:
    """Whether the line started before the first day of the normal window, so its earlier delivery is not loaded by itself."""
    return line_start < ingestion_window(today, window_days).start
