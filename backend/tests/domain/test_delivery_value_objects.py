from datetime import date
from decimal import Decimal

import pytest

from app.domain.value_objects.delivery import DeliveryDateRange
from tests.fixtures.delivery_rows import dsp_row


def test_date_range_is_inclusive_of_both_bounds():
    date_range = DeliveryDateRange(start=date(2026, 8, 1), end=date(2026, 8, 7))

    assert date_range.contains(date(2026, 8, 1))
    assert date_range.contains(date(2026, 8, 7))
    assert not date_range.contains(date(2026, 7, 31))
    assert not date_range.contains(date(2026, 8, 8))


def test_date_range_rejects_an_end_before_its_start():
    with pytest.raises(ValueError):
        DeliveryDateRange(start=date(2026, 8, 7), end=date(2026, 8, 1))


def test_date_range_lists_every_day_in_order():
    date_range = DeliveryDateRange(start=date(2026, 8, 1), end=date(2026, 8, 3))

    assert date_range.days() == [date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)]


def test_media_cost_must_be_a_decimal_never_a_float():
    with pytest.raises(TypeError):
        dsp_row(date(2026, 8, 1), media_cost=5.0)  # type: ignore[arg-type]


def test_a_delivery_row_keeps_media_cost_exact():
    row = dsp_row(date(2026, 8, 1), media_cost=Decimal("0.1") + Decimal("0.2"))

    assert row.media_cost == Decimal("0.3")
