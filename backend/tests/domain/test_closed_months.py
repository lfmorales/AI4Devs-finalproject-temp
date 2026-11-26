"""The days of an ingestion window that fall in a closed month (delivery/delivery-ingestion, `closed_month_days`)."""

from datetime import date

from app.domain.services.closed_months import days_in_closed_months
from app.domain.value_objects.delivery import DeliveryDateRange

ROLLING_WINDOW = DeliveryDateRange(date(2026, 11, 26), date(2026, 12, 2))


def test_the_rolling_window_counts_its_days_in_a_closed_november() -> None:
    assert days_in_closed_months(ROLLING_WINDOW, {(2026, 11)}) == 5


def test_a_window_with_no_closed_month_counts_none() -> None:
    assert days_in_closed_months(ROLLING_WINDOW, set()) == 0


def test_a_custom_range_counts_its_days_in_a_closed_october() -> None:
    assert days_in_closed_months(DeliveryDateRange(date(2026, 10, 15), date(2026, 11, 14)), {(2026, 10)}) == 17


def test_every_closed_month_of_the_window_is_counted_and_others_are_not() -> None:
    window = DeliveryDateRange(date(2026, 10, 15), date(2026, 12, 2))

    assert days_in_closed_months(window, {(2026, 10), (2026, 11), (2025, 11), (2027, 12)}) == 17 + 30


def test_the_same_month_of_another_year_is_not_closed() -> None:
    assert days_in_closed_months(ROLLING_WINDOW, {(2025, 11), (2027, 12)}) == 0


def test_a_single_day_window_in_a_closed_month_counts_one() -> None:
    assert days_in_closed_months(DeliveryDateRange(date(2026, 11, 30), date(2026, 11, 30)), [(2026, 11)]) == 1
