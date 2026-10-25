"""Re-running a date range replaces what the range held; it never appends to it."""

from datetime import date

import pytest

from app.domain.exceptions import DeliveryOutsideRangeError, DeliveryForUnknownLineError
from app.domain.services.delivery_range_replacement import DeliveryRangeReplacer
from app.domain.value_objects.delivery import DeliveryDateRange
from tests.fixtures.delivery_rows import daily_delivery
from tests.fixtures.in_memory_delivery_repository import InMemoryDeliveryRepository
from tests.fixtures.in_memory_unit_of_work import InMemoryUnitOfWork

LINE = 1
OTHER_LINE = 2
WINDOW = DeliveryDateRange(start=date(2026, 8, 2), end=date(2026, 8, 4))


def _window_run(impressions: int, days: tuple[int, ...] = (2, 3, 4), line: int = LINE):
    return [daily_delivery(line, date(2026, 8, day), impressions=impressions) for day in days]


def test_running_a_range_twice_yields_one_set_of_rows():
    repository = InMemoryDeliveryRepository()
    replacer = DeliveryRangeReplacer(InMemoryUnitOfWork(repository))

    replacer.replace_range([LINE], WINDOW, _window_run(1000))
    replacer.replace_range([LINE], WINDOW, _window_run(1000))

    assert len(repository.rows) == 3


def test_a_restated_figure_supersedes_the_earlier_one():
    repository = InMemoryDeliveryRepository()
    replacer = DeliveryRangeReplacer(InMemoryUnitOfWork(repository))
    replacer.replace_range([LINE], WINDOW, _window_run(1000))

    replacer.replace_range([LINE], WINDOW, _window_run(1250))

    assert set(repository.impressions_by_line_and_day().values()) == {1250}


def test_a_restatement_that_drops_a_day_removes_it():
    repository = InMemoryDeliveryRepository()
    replacer = DeliveryRangeReplacer(InMemoryUnitOfWork(repository))
    replacer.replace_range([LINE], WINDOW, _window_run(1000))

    replacer.replace_range([LINE], WINDOW, _window_run(1000, days=(2, 4)))

    assert [day for (_, day) in repository.impressions_by_line_and_day()] == [date(2026, 8, 2), date(2026, 8, 4)]


def test_delivery_outside_the_range_is_left_untouched():
    before_window = daily_delivery(LINE, date(2026, 8, 1), impressions=111)
    after_window = daily_delivery(LINE, date(2026, 8, 5), impressions=222)
    repository = InMemoryDeliveryRepository([before_window, after_window])

    DeliveryRangeReplacer(InMemoryUnitOfWork(repository)).replace_range([LINE], WINDOW, _window_run(1000))

    assert repository.rows[(LINE, date(2026, 8, 1))] == before_window
    assert repository.rows[(LINE, date(2026, 8, 5))] == after_window


def test_delivery_of_lines_not_in_the_run_is_left_untouched():
    other_line_in_window = daily_delivery(OTHER_LINE, date(2026, 8, 3), impressions=333)
    repository = InMemoryDeliveryRepository([other_line_in_window])

    DeliveryRangeReplacer(InMemoryUnitOfWork(repository)).replace_range([LINE], WINDOW, _window_run(1000))

    assert repository.rows[(OTHER_LINE, date(2026, 8, 3))] == other_line_in_window


def test_the_number_of_rows_stored_is_returned():
    stored = DeliveryRangeReplacer(InMemoryUnitOfWork(InMemoryDeliveryRepository())).replace_range([LINE], WINDOW, _window_run(1000))

    assert stored == 3


def test_a_row_dated_outside_the_range_is_rejected():
    replacer = DeliveryRangeReplacer(InMemoryUnitOfWork(InMemoryDeliveryRepository()))

    with pytest.raises(DeliveryOutsideRangeError):
        replacer.replace_range([LINE], WINDOW, _window_run(1000, days=(2, 9)))


def test_a_row_for_a_line_outside_the_run_is_rejected():
    replacer = DeliveryRangeReplacer(InMemoryUnitOfWork(InMemoryDeliveryRepository()))

    with pytest.raises(DeliveryForUnknownLineError):
        replacer.replace_range([LINE], WINDOW, _window_run(1000, line=OTHER_LINE))
