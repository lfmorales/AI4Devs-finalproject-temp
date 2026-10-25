"""Today as a calendar date in the configured zone, around midnight and the daylight saving changes."""

from datetime import UTC, date, datetime

import pytest

from app.domain.services.local_calendar import local_today

MADRID = "Europe/Madrid"


def _utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


def _today(instant: datetime, zone: str = MADRID) -> date:
    return local_today(zone, lambda: instant)


@pytest.mark.parametrize(
    ("instant_utc", "expected"),
    [
        # Summer (UTC+2): Madrid's midnight is 22:00 UTC.
        (_utc(2026, 8, 10, 19, 59), date(2026, 8, 10)),   # 21:59 in Madrid
        (_utc(2026, 8, 10, 20, 0), date(2026, 8, 10)),    # 22:00 in Madrid
        (_utc(2026, 8, 10, 21, 59), date(2026, 8, 10)),   # 23:59 in Madrid
        (_utc(2026, 8, 10, 22, 0), date(2026, 8, 11)),    # 00:00 in Madrid: already the next day
        (_utc(2026, 8, 11, 0, 0), date(2026, 8, 11)),     # 02:00 in Madrid
        # Winter (UTC+1): Madrid's midnight is 23:00 UTC.
        (_utc(2026, 12, 10, 22, 59), date(2026, 12, 10)),  # 23:59 in Madrid
        (_utc(2026, 12, 10, 23, 0), date(2026, 12, 11)),   # 00:00 in Madrid
    ],
)
def test_the_day_changes_at_midnight_in_madrid_not_in_utc(instant_utc, expected):
    assert _today(instant_utc) == expected


def test_the_utc_date_would_be_wrong_late_in_the_evening_in_madrid():
    instant = _utc(2026, 8, 10, 22, 30)  # 00:30 on the 11th in Madrid, still the 10th in UTC

    assert instant.date() == date(2026, 8, 10)
    assert _today(instant) == date(2026, 8, 11)


@pytest.mark.parametrize(
    ("instant_utc", "expected"),
    [
        # Spring forward, 29 March 2026: 02:00 Madrid becomes 03:00 at 01:00 UTC.
        (_utc(2026, 3, 28, 22, 59), date(2026, 3, 28)),   # 23:59 on the 28th
        (_utc(2026, 3, 28, 23, 0), date(2026, 3, 29)),    # 00:00 on the 29th (UTC+1)
        (_utc(2026, 3, 29, 0, 59), date(2026, 3, 29)),    # 01:59, just before the change
        (_utc(2026, 3, 29, 1, 0), date(2026, 3, 29)),     # 03:00, just after the change
        (_utc(2026, 3, 29, 21, 59), date(2026, 3, 29)),   # 23:59 on the 29th (UTC+2)
        (_utc(2026, 3, 29, 22, 0), date(2026, 3, 30)),
        # Fall back, 25 October 2026: 03:00 Madrid becomes 02:00 at 01:00 UTC.
        (_utc(2026, 10, 24, 21, 59), date(2026, 10, 24)),  # 23:59 on the 24th (UTC+2)
        (_utc(2026, 10, 24, 22, 0), date(2026, 10, 25)),   # 00:00 on the 25th
        (_utc(2026, 10, 25, 0, 59), date(2026, 10, 25)),   # 02:59 the first time
        (_utc(2026, 10, 25, 1, 0), date(2026, 10, 25)),    # 02:00 the second time
        (_utc(2026, 10, 25, 22, 59), date(2026, 10, 25)),  # 23:59 on the 25th (UTC+1)
        (_utc(2026, 10, 25, 23, 0), date(2026, 10, 26)),
    ],
)
def test_the_clock_changes_do_not_move_or_repeat_a_day(instant_utc, expected):
    assert _today(instant_utc) == expected


def test_another_zone_can_be_configured():
    instant = _utc(2026, 8, 10, 23, 30)

    assert _today(instant, "UTC") == date(2026, 8, 10)
    assert _today(instant, "Asia/Tokyo") == date(2026, 8, 11)


def test_an_unknown_zone_is_rejected():
    with pytest.raises(ValueError, match="time zone"):
        local_today("Not/AZone", lambda: _utc(2026, 8, 10))


def test_a_naive_instant_is_rejected_rather_than_guessed():
    with pytest.raises(ValueError, match="timezone-aware"):
        local_today(MADRID, lambda: datetime(2026, 8, 10, 12, 0))
