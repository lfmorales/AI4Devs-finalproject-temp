from collections.abc import Callable
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def utc_now() -> datetime:
    return datetime.now(UTC)


def local_today(zone_name: str, clock: Callable[[], datetime] = utc_now) -> date:
    """The calendar date it is now in the named zone. The one place "today" is decided.

    The date is read from the zone's own clock, so daylight saving changes need no special case.
    """
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"unknown time zone: {zone_name!r}") from None
    instant = clock()
    if instant.tzinfo is None:
        raise ValueError("the clock must return a timezone-aware datetime")
    return instant.astimezone(zone).date()
