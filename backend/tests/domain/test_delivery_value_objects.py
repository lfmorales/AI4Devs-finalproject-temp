from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.domain.value_objects.delivery import DeliveryDateRange
from tests.fixtures.delivery_rows import daily_delivery, dsp_row


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


def test_a_delivery_row_carries_ots_as_a_decimal_and_completions_as_an_integer() -> None:
    row = dsp_row(date(2026, 8, 1), ots=Decimal("7500.1234"), video_completions=40615)

    assert row.ots == Decimal("7500.1234")
    assert row.video_completions == 40615


def test_a_delivery_row_without_them_reports_zero_ots_and_zero_completions() -> None:
    row = dsp_row(date(2026, 8, 1))

    assert (row.ots, row.video_completions) == (Decimal(0), 0)


AMOUNTS = ("buyer_spend", "reported_revenue", "third_party_data_cost", "audience_data_cost")


def test_a_delivery_row_carries_the_four_amounts_exactly() -> None:
    row = dsp_row(
        date(2026, 11, 19), buyer_spend=Decimal("338.954"), reported_revenue=Decimal("271.1632"),
        third_party_data_cost=Decimal("0"), audience_data_cost=Decimal("1.25"),
    )

    assert (row.buyer_spend, row.reported_revenue, row.third_party_data_cost, row.audience_data_cost) == (
        Decimal("338.954"), Decimal("271.1632"), Decimal(0), Decimal("1.25"),
    )


def test_a_delivery_row_without_them_reports_zero_in_the_four_amounts() -> None:
    row = dsp_row(date(2026, 11, 19))

    assert all(getattr(row, amount) == Decimal(0) for amount in AMOUNTS)


@pytest.mark.parametrize("amount", AMOUNTS)
def test_each_amount_of_a_delivery_row_must_be_a_decimal_never_a_float(amount: str) -> None:
    a_float: dict[str, Any] = {amount: 271.1632}

    with pytest.raises(TypeError, match=f"{amount} must be Decimal"):
        dsp_row(date(2026, 11, 19), **a_float)


def test_a_daily_delivery_carries_the_four_amounts_exactly() -> None:
    delivery = daily_delivery(
        1, date(2026, 11, 19), buyer_spend=Decimal("338.954"), reported_revenue=Decimal("271.1632"),
        third_party_data_cost=Decimal("0.5"), audience_data_cost=Decimal("1.25"),
    )

    assert (delivery.buyer_spend, delivery.reported_revenue) == (Decimal("338.954"), Decimal("271.1632"))
    assert (delivery.third_party_data_cost, delivery.audience_data_cost) == (Decimal("0.5"), Decimal("1.25"))


@pytest.mark.parametrize("amount", AMOUNTS)
def test_each_amount_of_a_daily_delivery_must_be_a_decimal_never_a_float(amount: str) -> None:
    a_float: dict[str, Any] = {amount: 1.25}

    with pytest.raises(TypeError, match=f"{amount} must be Decimal"):
        daily_delivery(1, date(2026, 11, 19), **a_float)
