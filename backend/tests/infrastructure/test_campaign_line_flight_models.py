"""Flights (campaign_line_periods) and the columns that start moving a line under its campaign."""

from datetime import date

import pytest
from sqlalchemy import inspect, select, update
from sqlalchemy.exc import IntegrityError

from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
)
from tests.fixtures.delivery_data import campaign_id_of, insert_campaign_line


def _flight(line_id: int, period_id: int, **overrides: object) -> CampaignLinePeriodRecord:
    fields: dict[str, object] = {
        "campaign_line_id": line_id,
        "campaign_period_id": period_id,
        "flight_start": date(2026, 8, 1),
        "flight_end": date(2026, 8, 31),
        "contracted_impressions": 1000,
    }
    fields.update(overrides)
    return CampaignLinePeriodRecord(**fields)


def _period_id_of(session, line_id: int) -> int:
    return session.scalar(select(CampaignLineRecord.campaign_period_id).where(CampaignLineRecord.id == line_id))


def _second_line_of_the_same_campaign(session, line_id: int) -> int:
    first = session.get(CampaignLineRecord, line_id)
    second = CampaignLineRecord(
        campaign_period_id=first.campaign_period_id, dsp_id=first.dsp_id, channel_id=first.channel_id,
        format_id=first.format_id, scope="national", market_description="Nacional",
        contracted_impressions=10, sale_cpm=first.sale_cpm,
    )
    session.add(second)
    session.flush()
    return second.id


def test_a_flight_is_stored_with_its_window_and_volume(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    rolled_back_session.add(_flight(line_id, _period_id_of(rolled_back_session, line_id)))
    rolled_back_session.flush()

    stored = rolled_back_session.scalars(select(CampaignLinePeriodRecord)).one()

    assert (stored.flight_start, stored.flight_end, stored.contracted_impressions) == (
        date(2026, 8, 1), date(2026, 8, 31), 1000,
    )


def test_a_line_has_at_most_one_flight_per_period(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    period_id = _period_id_of(rolled_back_session, line_id)
    rolled_back_session.add(_flight(line_id, period_id))
    rolled_back_session.flush()

    rolled_back_session.add(_flight(line_id, period_id, contracted_impressions=5))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_two_lines_can_have_a_flight_in_the_same_period(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    period_id = _period_id_of(rolled_back_session, line_id)
    other_line_id = _second_line_of_the_same_campaign(rolled_back_session, line_id)

    rolled_back_session.add_all([_flight(line_id, period_id), _flight(other_line_id, period_id)])
    rolled_back_session.flush()


def test_a_flight_cannot_end_before_it_starts(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    rolled_back_session.add(
        _flight(line_id, _period_id_of(rolled_back_session, line_id),
                flight_start=date(2026, 8, 10), flight_end=date(2026, 8, 9))
    )

    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_a_flight_of_a_single_day_is_allowed(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    rolled_back_session.add(
        _flight(line_id, _period_id_of(rolled_back_session, line_id),
                flight_start=date(2026, 8, 10), flight_end=date(2026, 8, 10))
    )
    rolled_back_session.flush()


def test_a_flight_must_reference_an_existing_line(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    period_id = _period_id_of(rolled_back_session, line_id)

    rolled_back_session.add(_flight(0, period_id))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_a_flight_must_reference_an_existing_period(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)

    rolled_back_session.add(_flight(line_id, 0))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_the_new_line_columns_are_optional_for_now(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)

    line = rolled_back_session.get(CampaignLineRecord, line_id)

    assert (line.campaign_id, line.line_number, line.start_date, line.end_date) == (None, None, None, None)


def test_a_campaign_cannot_repeat_a_line_number(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    other_line_id = _second_line_of_the_same_campaign(rolled_back_session, line_id)
    campaign_id = campaign_id_of(rolled_back_session, line_id)
    rolled_back_session.execute(
        update(CampaignLineRecord).where(CampaignLineRecord.id == line_id).values(campaign_id=campaign_id, line_number=1)
    )
    rolled_back_session.flush()

    with pytest.raises(IntegrityError):
        rolled_back_session.execute(
            update(CampaignLineRecord).where(CampaignLineRecord.id == other_line_id)
            .values(campaign_id=campaign_id, line_number=1)
        )


def test_lines_without_a_campaign_or_a_number_do_not_collide(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    other_line_id = _second_line_of_the_same_campaign(rolled_back_session, line_id)
    campaign_id = campaign_id_of(rolled_back_session, line_id)

    # Both rows keep a null number, and a numbered line may coexist with an unnumbered one.
    rolled_back_session.execute(
        update(CampaignLineRecord).where(CampaignLineRecord.id == line_id).values(campaign_id=campaign_id, line_number=None)
    )
    rolled_back_session.execute(
        update(CampaignLineRecord).where(CampaignLineRecord.id == other_line_id).values(campaign_id=campaign_id, line_number=None)
    )
    rolled_back_session.flush()


def test_a_line_number_is_reusable_across_campaigns(rolled_back_session):
    first_line = insert_campaign_line(rolled_back_session, campaign_name="First campaign")
    second_line = insert_campaign_line(rolled_back_session, campaign_name="Second campaign")
    for line_id in (first_line, second_line):
        rolled_back_session.execute(
            update(CampaignLineRecord).where(CampaignLineRecord.id == line_id)
            .values(campaign_id=campaign_id_of(rolled_back_session, line_id), line_number=1)
        )
    rolled_back_session.flush()


def test_the_line_dates_are_stored_when_given(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    rolled_back_session.execute(
        update(CampaignLineRecord).where(CampaignLineRecord.id == line_id)
        .values(start_date=date(2026, 8, 5), end_date=date(2026, 8, 20))
    )
    rolled_back_session.flush()
    rolled_back_session.expire_all()

    line = rolled_back_session.get(CampaignLineRecord, line_id)

    assert (line.start_date, line.end_date) == (date(2026, 8, 5), date(2026, 8, 20))


def test_the_partial_unique_index_exists_and_covers_campaign_and_number(rolled_back_session):
    indexes = {index["name"]: index for index in inspect(rolled_back_session.get_bind()).get_indexes("campaign_lines")}

    index = indexes["uq_campaign_lines_campaign_line_number"]

    assert index["unique"] is True
    assert index["column_names"] == ["campaign_id", "line_number"]
