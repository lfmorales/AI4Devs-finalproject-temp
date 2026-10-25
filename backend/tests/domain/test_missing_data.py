"""An active campaign is missing data when its latest delivery predates D-1, D being the day of the run."""

from datetime import date

from app.domain.services.missing_data import has_missing_data

TODAY = date(2026, 8, 10)
D_MINUS_1 = date(2026, 8, 9)


def test_a_latest_delivery_older_than_d_minus_1_is_flagged():
    assert has_missing_data(latest_delivery_date=date(2026, 8, 8), today=TODAY) is True


def test_a_latest_delivery_at_d_minus_1_is_not_flagged():
    assert has_missing_data(latest_delivery_date=D_MINUS_1, today=TODAY) is False


def test_a_latest_delivery_after_d_minus_1_is_not_flagged():
    assert has_missing_data(latest_delivery_date=TODAY, today=TODAY) is False


def test_a_campaign_that_never_delivered_is_flagged():
    assert has_missing_data(latest_delivery_date=None, today=TODAY) is True


def test_the_flag_clears_when_the_next_ingestion_brings_delivery_for_the_latest_day():
    stalled = has_missing_data(latest_delivery_date=date(2026, 8, 7), today=TODAY)
    after_next_ingestion = has_missing_data(latest_delivery_date=D_MINUS_1, today=TODAY)

    assert (stalled, after_next_ingestion) == (True, False)


def test_the_same_delivery_date_is_flagged_once_a_further_day_passes_without_data():
    assert has_missing_data(latest_delivery_date=D_MINUS_1, today=date(2026, 8, 11)) is True
