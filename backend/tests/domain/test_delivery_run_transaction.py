"""A run lands whole or not at all: a failure partway leaves the stored range as it was."""

from collections.abc import Iterator
from datetime import date

import pytest

from app.domain.services.delivery_range_replacement import DeliveryRangeReplacer
from app.domain.value_objects.delivery import DailyDelivery, DeliveryDateRange
from tests.fixtures.delivery_rows import daily_delivery
from tests.fixtures.in_memory_delivery_repository import InMemoryDeliveryRepository
from tests.fixtures.in_memory_unit_of_work import InMemoryUnitOfWork

LINE = 1
WINDOW = DeliveryDateRange(start=date(2026, 8, 2), end=date(2026, 8, 4))


class DspConnectionLost(Exception):
    """Stands in for any failure while the DSP report is still being read."""


def _stream_failing_after(good_rows: int) -> Iterator[DailyDelivery]:
    for day in range(2, 2 + good_rows):
        yield daily_delivery(LINE, date(2026, 8, day), impressions=9999)
    raise DspConnectionLost()


def _previous_run() -> list[DailyDelivery]:
    return [daily_delivery(LINE, date(2026, 8, day), impressions=1000) for day in (2, 3, 4)]


def test_a_run_that_fails_partway_leaves_the_previous_range_intact():
    repository = InMemoryDeliveryRepository(_previous_run())
    before = dict(repository.rows)
    replacer = DeliveryRangeReplacer(InMemoryUnitOfWork(repository))

    with pytest.raises(DspConnectionLost):
        replacer.replace_range([LINE], WINDOW, _stream_failing_after(good_rows=2))

    assert repository.rows == before


def test_a_run_that_fails_partway_stores_no_part_of_a_new_range():
    repository = InMemoryDeliveryRepository()
    replacer = DeliveryRangeReplacer(InMemoryUnitOfWork(repository))

    with pytest.raises(DspConnectionLost):
        replacer.replace_range([LINE], WINDOW, _stream_failing_after(good_rows=2))

    assert repository.rows == {}


def test_a_failed_run_rolls_back_and_never_commits():
    unit_of_work = InMemoryUnitOfWork(InMemoryDeliveryRepository())

    with pytest.raises(DspConnectionLost):
        DeliveryRangeReplacer(unit_of_work).replace_range([LINE], WINDOW, _stream_failing_after(good_rows=1))

    assert (unit_of_work.rollback_count, unit_of_work.commit_count) == (1, 0)


def test_a_successful_run_deletes_and_inserts_in_one_transaction_and_commits_once():
    unit_of_work = InMemoryUnitOfWork(InMemoryDeliveryRepository(_previous_run()))

    DeliveryRangeReplacer(unit_of_work).replace_range([LINE], WINDOW, _previous_run())

    assert (unit_of_work.entered_count, unit_of_work.commit_count, unit_of_work.rollback_count) == (1, 1, 0)
