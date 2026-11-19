"""Pacing compares delivered volume with what a linear delivery would have reached by a date.

Worked example used below: 3,100 impressions over August (31 days). By the end of August 10th
ten days have elapsed, so 1,000 impressions are expected.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.services.pacing import PacingResult, PacingStatus, calculate_pacing

AUGUST_START = date(2026, 8, 1)
AUGUST_END = date(2026, 8, 31)
AUGUST_10 = date(2026, 8, 10)


def _pace(delivered: int, as_of: date = AUGUST_10, contracted: int = 3100):
    return calculate_pacing(
        contracted_impressions=contracted,
        period_start=AUGUST_START,
        period_end=AUGUST_END,
        as_of=as_of,
        delivered=Decimal(delivered),
    )


def test_expected_volume_is_linear_over_the_days_elapsed_including_the_as_of_day():
    assert _pace(delivered=1000).expected_impressions == 1000


def test_under_delivery_beyond_ten_percent_is_flagged():
    pacing = _pace(delivered=899)

    assert pacing.status is PacingStatus.UNDER_DELIVERING
    assert pacing.is_deviating is True


def test_over_delivery_beyond_ten_percent_is_flagged():
    pacing = _pace(delivered=1101)

    assert pacing.status is PacingStatus.OVER_DELIVERING
    assert pacing.is_deviating is True


def test_exactly_ten_percent_under_is_inside_the_threshold():
    assert _pace(delivered=900).status is PacingStatus.ON_PACE


def test_exactly_ten_percent_over_is_inside_the_threshold():
    assert _pace(delivered=1100).status is PacingStatus.ON_PACE


@pytest.mark.parametrize("delivered", [950, 1000, 1050])
def test_delivery_inside_the_threshold_is_not_flagged(delivered):
    assert _pace(delivered=delivered).is_deviating is False


def test_the_boundary_is_exact_when_the_expected_volume_does_not_terminate():
    # 10 impressions over 3 days, 1 day elapsed: expected 3.333..., and 3 is exactly 10% below it.
    pacing = calculate_pacing(
        contracted_impressions=10,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 3),
        as_of=date(2026, 8, 1),
        delivered=Decimal(3),
    )

    assert pacing.status is PacingStatus.ON_PACE


def test_days_remaining_counts_the_days_after_the_as_of_day():
    assert _pace(delivered=1000).days_remaining == 21


def test_a_flagged_line_reports_the_days_remaining():
    assert _pace(delivered=100).days_remaining == 21


def test_after_the_period_ends_the_whole_contracted_volume_is_expected_and_no_days_remain():
    pacing = _pace(delivered=3100, as_of=date(2026, 9, 5))

    assert (pacing.expected_impressions, pacing.days_remaining) == (3100, 0)


def test_before_the_period_starts_nothing_is_expected_and_nothing_is_flagged():
    pacing = _pace(delivered=0, as_of=date(2026, 7, 20))

    assert (pacing.expected_impressions, pacing.status, pacing.deviation) == (0, PacingStatus.ON_PACE, None)


def test_a_period_that_has_ended_with_nothing_delivered_reports_under_delivery():
    # The pure function does not know which periods the status view lists; finished periods are left out there.
    pacing = _pace(delivered=0, as_of=date(2026, 9, 5))

    assert (pacing.status, pacing.is_deviating, pacing.days_remaining) == (PacingStatus.UNDER_DELIVERING, True, 0)


def test_a_line_with_no_contracted_volume_is_never_flagged():
    assert _pace(delivered=500, contracted=0).is_deviating is False


def test_deviation_is_the_signed_ratio_to_the_expected_volume():
    assert _pace(delivered=800).deviation == Decimal("-0.2")


def test_a_period_ending_before_it_starts_is_rejected():
    with pytest.raises(ValueError):
        calculate_pacing(100, AUGUST_END, AUGUST_START, AUGUST_10, Decimal(0))


@pytest.mark.parametrize("contracted, delivered", [(-1, 0), (0, -1)])
def test_negative_volumes_are_rejected(contracted, delivered):
    with pytest.raises(ValueError):
        calculate_pacing(contracted, AUGUST_START, AUGUST_END, AUGUST_10, Decimal(delivered))


# A DOOH line: 300,000 OTS over September (30 days). By the end of September 10th ten days have elapsed,
# so 100,000 OTS are expected. The volumes carry decimals: OTS is an absolute count with four decimals.
SEPTEMBER_START = date(2026, 9, 1)
SEPTEMBER_END = date(2026, 9, 30)
SEPTEMBER_10 = date(2026, 9, 10)


def _pace_ots(delivered: str) -> PacingResult:
    return calculate_pacing(300_000, SEPTEMBER_START, SEPTEMBER_END, SEPTEMBER_10, Decimal(delivered))


def test_95000_75_ots_of_100000_expected_is_minus_4_99925_percent_and_on_pace() -> None:
    pacing = _pace_ots("95000.75")

    assert pacing.deviation == Decimal("-0.0499925")
    assert pacing.status is PacingStatus.ON_PACE
    assert pacing.is_deviating is False


def test_exactly_ten_percent_under_in_ots_is_on_pace() -> None:
    pacing = _pace_ots("90000.0000")

    assert pacing.deviation == Decimal("-0.1")
    assert pacing.status is PacingStatus.ON_PACE


def test_a_half_ots_beyond_ten_percent_under_is_under_delivering_with_the_days_remaining() -> None:
    pacing = _pace_ots("89999.5000")

    assert pacing.deviation == Decimal("-0.100005")
    assert pacing.status is PacingStatus.UNDER_DELIVERING
    assert pacing.days_remaining == 20


def test_exactly_ten_percent_over_in_ots_is_on_pace_and_a_half_ots_more_is_not() -> None:
    assert _pace_ots("110000.0000").status is PacingStatus.ON_PACE
    assert _pace_ots("110000.5000").status is PacingStatus.OVER_DELIVERING


def test_a_decimal_volume_is_compared_exactly_without_going_through_float() -> None:
    # 0.1 + 0.2 style traps: 89999.9999 is under the 90,000 boundary by one ten-thousandth only.
    assert _pace_ots("89999.9999").status is PacingStatus.UNDER_DELIVERING
    assert _pace_ots("90000.0001").status is PacingStatus.ON_PACE


def test_a_negative_decimal_volume_is_rejected() -> None:
    with pytest.raises(ValueError):
        _pace_ots("-0.0001")
