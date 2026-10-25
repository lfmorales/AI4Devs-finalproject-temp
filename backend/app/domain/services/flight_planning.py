from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.domain.entities.campaign import CampaignPeriod
from app.domain.exceptions import VolumeTooSmallForFlightsError
from app.domain.services.flight_generation import generate_flights
from app.domain.services.line_dates import validate_line_dates
from app.domain.services.volume_distribution import distribute_volume_by_days
from app.domain.value_objects.flight import FlightWindow


@dataclass(frozen=True)
class LineWindows:
    """A line's effective dates and the flight windows they produce."""

    start_date: date
    end_date: date
    windows: tuple[FlightWindow, ...]


def resolve_line_windows(
    line_start: date | None,
    line_end: date | None,
    campaign_start: date,
    campaign_end: date,
    periods: Sequence[CampaignPeriod],
) -> LineWindows:
    """Complete a line's dates from the campaign's, check them, and generate its flight windows.

    Shared by the registration and the preview, so both apply the same rule.
    """
    start = line_start or campaign_start
    end = line_end or campaign_end
    validate_line_dates(start, end, campaign_start, campaign_end)
    return LineWindows(start, end, tuple(generate_flights(start, end, periods)))


def split_volume_by_days(total: int, windows: Sequence[FlightWindow]) -> tuple[int, ...]:
    """Split a volume by days, refusing a split that leaves a flight without impressions."""
    volumes = distribute_volume_by_days(total, windows)
    if min(volumes) == 0:
        raise VolumeTooSmallForFlightsError("a flight would carry no impressions")
    return volumes
