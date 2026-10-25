from collections.abc import Sequence

from app.domain.value_objects.flight import FlightWindow


def distribute_volume_by_days(total: int, windows: Sequence[FlightWindow]) -> tuple[int, ...]:
    """Split a line's volume across its flight windows in proportion to their days, in whole impressions.

    Each window takes the floor of its share. The impressions left over go one by one to the windows
    with the largest fractional remainder, the earliest window first on a tie, so the parts always add
    up to the total. Windows are expected in chronological order. A total smaller than the number of
    windows can leave a window with nothing.
    """
    if total < 0:
        raise ValueError("total volume cannot be negative")
    if not windows:
        raise ValueError("at least one flight window is needed")

    total_days = sum(window.days for window in windows)
    shares = [total * window.days // total_days for window in windows]
    remainders = [total * window.days % total_days for window in windows]

    leftover = total - sum(shares)
    by_remainder = sorted(range(len(windows)), key=lambda index: (-remainders[index], index))
    for index in by_remainder[:leftover]:
        shares[index] += 1
    return tuple(shares)
