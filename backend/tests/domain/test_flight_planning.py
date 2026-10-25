from datetime import date

import pytest

from app.domain.exceptions import LineDatesInvalidError, LineDatesOutsideCampaignError, VolumeTooSmallForFlightsError
from app.domain.services.flight_planning import resolve_line_windows, split_volume_by_days
from app.domain.services.period_expansion import PeriodExpansionService
from app.domain.value_objects.flight import FlightWindow

CAMPAIGN_START = date(2026, 8, 1)
CAMPAIGN_END = date(2026, 10, 31)
PERIODS = PeriodExpansionService().expand(CAMPAIGN_START, CAMPAIGN_END)


def _resolve(line_start=None, line_end=None):
    return resolve_line_windows(line_start, line_end, CAMPAIGN_START, CAMPAIGN_END, PERIODS)


def test_a_line_without_dates_takes_the_campaign_dates_and_a_window_per_month():
    plan = _resolve()

    assert (plan.start_date, plan.end_date) == (CAMPAIGN_START, CAMPAIGN_END)
    assert [(w.period_month, w.days) for w in plan.windows] == [(8, 31), (9, 30), (10, 31)]


def test_a_line_with_one_date_completes_the_other_from_the_campaign():
    plan = _resolve(line_start=date(2026, 9, 10))

    assert (plan.start_date, plan.end_date) == (date(2026, 9, 10), CAMPAIGN_END)
    assert [w.period_month for w in plan.windows] == [9, 10]


def test_a_line_with_its_own_dates_gets_the_windows_it_touches():
    plan = _resolve(date(2026, 9, 10), date(2026, 10, 5))

    assert plan.windows == (
        FlightWindow(2026, 9, date(2026, 9, 10), date(2026, 9, 30)),
        FlightWindow(2026, 10, date(2026, 10, 1), date(2026, 10, 5)),
    )


def test_dates_outside_the_campaign_are_refused():
    with pytest.raises(LineDatesOutsideCampaignError):
        _resolve(date(2026, 7, 31), CAMPAIGN_END)


def test_inverted_dates_are_refused():
    with pytest.raises(LineDatesInvalidError):
        _resolve(date(2026, 9, 2), date(2026, 9, 1))


def test_a_start_after_the_campaign_end_with_no_end_is_invalid_dates():
    with pytest.raises(LineDatesInvalidError):
        _resolve(line_start=date(2026, 11, 5))


def test_the_split_follows_the_days_of_each_window():
    assert split_volume_by_days(100, _resolve().windows) == (34, 32, 34)


def test_a_split_that_leaves_a_window_at_zero_is_refused():
    with pytest.raises(VolumeTooSmallForFlightsError):
        split_volume_by_days(2, _resolve().windows)


def test_a_split_where_every_window_gets_one_is_accepted():
    assert sorted(split_volume_by_days(3, _resolve().windows)) == [1, 1, 1]
