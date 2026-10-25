import random
from datetime import date

import pytest

from app.domain.services.volume_distribution import distribute_volume_by_days
from app.domain.value_objects.flight import FlightWindow


def _window(year: int, month: int, first_day: int, last_day: int) -> FlightWindow:
    return FlightWindow(year, month, date(year, month, first_day), date(year, month, last_day))


def test_a_window_counts_both_of_its_ends():
    assert _window(2026, 8, 1, 31).days == 31
    assert _window(2026, 8, 20, 20).days == 1


def test_a_window_cannot_end_before_it_starts():
    with pytest.raises(ValueError):
        FlightWindow(2026, 8, date(2026, 8, 10), date(2026, 8, 9))


def test_one_hundred_impressions_over_31_30_and_31_days_follow_the_largest_remainders():
    windows = [_window(2026, 8, 1, 31), _window(2026, 9, 1, 30), _window(2026, 10, 1, 31)]

    # 100 * 31/92 = 33.69, 100 * 30/92 = 32.60: the two spare impressions go to the 0.69 shares.
    assert distribute_volume_by_days(100, windows) == (34, 32, 34)


def test_a_window_clipped_to_half_a_month_carries_a_smaller_share():
    windows = [_window(2026, 8, 16, 31), _window(2026, 9, 1, 30)]  # 16 and 30 days

    shares = distribute_volume_by_days(46_000, windows)

    assert shares == (16_000, 30_000)


def test_a_single_window_carries_the_whole_volume():
    assert distribute_volume_by_days(12_345, [_window(2026, 8, 5, 9)]) == (12_345,)


def test_a_tie_between_remainders_goes_to_the_earliest_month():
    windows = [_window(2026, 8, 1, 31), _window(2026, 10, 1, 31)]  # equal days

    assert distribute_volume_by_days(3, windows) == (2, 1)


def test_the_earliest_window_wins_a_tie_whatever_its_position_among_equal_remainders():
    windows = [_window(2026, 7, 1, 31), _window(2026, 8, 1, 31), _window(2026, 10, 1, 31)]

    assert distribute_volume_by_days(1, windows) == (1, 0, 0)
    assert distribute_volume_by_days(2, windows) == (1, 1, 0)


def test_a_zero_volume_is_split_into_zeros():
    assert distribute_volume_by_days(0, [_window(2026, 8, 1, 31), _window(2026, 9, 1, 30)]) == (0, 0)


def test_the_parts_always_add_up_to_the_total():
    generator = random.Random(20261025)
    for _ in range(500):
        windows = []
        for month in range(1, generator.randint(1, 12) + 1):
            last_day_of_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
            first_day = generator.randint(1, last_day_of_month)
            windows.append(_window(2026, month, first_day, generator.randint(first_day, last_day_of_month)))
        total = generator.randint(0, 10_000_000)

        shares = distribute_volume_by_days(total, windows)

        assert sum(shares) == total
        assert all(share >= 0 for share in shares)
        # No window is more than one impression away from its exact proportional share.
        total_days = sum(window.days for window in windows)
        for window, share in zip(windows, shares):
            assert abs(share - total * window.days / total_days) < 1


def test_a_negative_volume_is_refused():
    with pytest.raises(ValueError):
        distribute_volume_by_days(-1, [_window(2026, 8, 1, 31)])


def test_at_least_one_window_is_needed():
    with pytest.raises(ValueError):
        distribute_volume_by_days(10, [])
