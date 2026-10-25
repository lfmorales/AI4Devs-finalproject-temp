from datetime import date

import pytest

from app.domain.exceptions import DomainError, LineDatesOutsideCampaignError
from app.domain.services.line_dates import validate_line_dates

CAMPAIGN_START = date(2026, 8, 10)
CAMPAIGN_END = date(2026, 10, 20)


def test_dates_equal_to_the_campaign_are_accepted():
    validate_line_dates(CAMPAIGN_START, CAMPAIGN_END, CAMPAIGN_START, CAMPAIGN_END)


def test_dates_inside_the_campaign_are_accepted():
    validate_line_dates(date(2026, 8, 11), date(2026, 10, 19), CAMPAIGN_START, CAMPAIGN_END)


def test_a_single_day_on_either_edge_is_accepted():
    validate_line_dates(CAMPAIGN_START, CAMPAIGN_START, CAMPAIGN_START, CAMPAIGN_END)
    validate_line_dates(CAMPAIGN_END, CAMPAIGN_END, CAMPAIGN_START, CAMPAIGN_END)


def test_a_line_starting_the_day_before_the_campaign_is_refused():
    with pytest.raises(LineDatesOutsideCampaignError):
        validate_line_dates(date(2026, 8, 9), CAMPAIGN_END, CAMPAIGN_START, CAMPAIGN_END)


def test_a_line_ending_the_day_after_the_campaign_is_refused():
    with pytest.raises(LineDatesOutsideCampaignError):
        validate_line_dates(CAMPAIGN_START, date(2026, 10, 21), CAMPAIGN_START, CAMPAIGN_END)


def test_a_line_entirely_outside_the_campaign_is_refused():
    with pytest.raises(LineDatesOutsideCampaignError):
        validate_line_dates(date(2027, 1, 1), date(2027, 1, 31), CAMPAIGN_START, CAMPAIGN_END)


def test_the_error_is_a_domain_error():
    assert issubclass(LineDatesOutsideCampaignError, DomainError)


def test_a_line_ending_before_it_starts_is_refused_as_a_plain_value_error():
    with pytest.raises(ValueError):
        validate_line_dates(date(2026, 9, 2), date(2026, 9, 1), CAMPAIGN_START, CAMPAIGN_END)
