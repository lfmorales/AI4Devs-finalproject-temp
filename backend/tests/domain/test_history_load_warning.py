"""A line that started before the normal window needs a history load: the window does not reach its first days."""

from datetime import date

import pytest

from app.domain.value_objects.ingestion import needs_history_load

TODAY = date(2026, 8, 20)


def test_a_line_that_started_the_day_before_the_window_starts_needs_a_history_load():
    assert needs_history_load(date(2026, 8, 12), TODAY) is True


def test_a_line_that_started_on_the_first_day_of_the_window_does_not():
    assert needs_history_load(date(2026, 8, 13), TODAY) is False


@pytest.mark.parametrize("start", [date(2026, 8, 19), date(2026, 8, 20), date(2026, 9, 1)])
def test_a_recent_or_future_line_does_not(start):
    assert needs_history_load(start, TODAY) is False


def test_a_long_running_line_does_and_the_window_length_is_configurable():
    assert needs_history_load(date(2026, 1, 1), TODAY) is True
    assert needs_history_load(date(2026, 8, 15), TODAY, window_days=3) is True
    assert needs_history_load(date(2026, 8, 17), TODAY, window_days=3) is False
