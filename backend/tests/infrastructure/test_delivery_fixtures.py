"""The shared delivery fixtures build the new line model: a line under its campaign, with dates and a flight."""

from datetime import date

from sqlalchemy import select

from app.infrastructure.persistence.models.campaign import CampaignLinePeriodRecord, CampaignLineRecord
from tests.fixtures.delivery_data import CONTRACTED_IMPRESSIONS, campaign_id_of, insert_campaign_line


def test_the_line_hangs_from_its_campaign_with_a_number_and_the_campaign_dates(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session, start_date=date(2026, 8, 1), end_date=date(2026, 8, 31))

    line = rolled_back_session.get(CampaignLineRecord, line_id)

    assert line.campaign_id == campaign_id_of(rolled_back_session, line_id)
    assert (line.line_number, line.start_date, line.end_date) == (1, date(2026, 8, 1), date(2026, 8, 31))


def test_the_line_has_one_flight_over_its_dates_carrying_the_contracted_volume(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session, start_date=date(2026, 8, 3), end_date=date(2026, 8, 20))

    flight = rolled_back_session.scalars(
        select(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.campaign_line_id == line_id)
    ).one()

    assert (flight.flight_start, flight.flight_end) == (date(2026, 8, 3), date(2026, 8, 20))
    assert flight.contracted_impressions == CONTRACTED_IMPRESSIONS


def test_the_line_may_run_for_less_than_its_campaign(rolled_back_session):
    line_id = insert_campaign_line(
        rolled_back_session, start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
        line_start=date(2026, 8, 10), line_end=date(2026, 8, 20),
    )

    line = rolled_back_session.get(CampaignLineRecord, line_id)
    flight = rolled_back_session.scalars(select(CampaignLinePeriodRecord)).one()

    assert (line.start_date, line.end_date) == (date(2026, 8, 10), date(2026, 8, 20))
    assert (flight.flight_start, flight.flight_end) == (date(2026, 8, 10), date(2026, 8, 20))


def test_two_campaigns_do_not_share_ids_or_numbers(rolled_back_session):
    first = insert_campaign_line(rolled_back_session, campaign_name="First fixture")
    second = insert_campaign_line(rolled_back_session, campaign_name="Second fixture")

    assert campaign_id_of(rolled_back_session, first) != campaign_id_of(rolled_back_session, second)
    assert rolled_back_session.get(CampaignLineRecord, second).line_number == 1
