"""Which lines the absence check evaluates, against PostgreSQL. Today is 2026-08-10, so the window is Aug 3 to Aug 9."""

from datetime import date, datetime

import pytest

from app.domain.value_objects.delivery import DeliveryDateRange
from app.domain.value_objects.ingestion import MissingDeliveryCandidate
from sqlalchemy import select

from app.infrastructure.persistence.models.campaign import CampaignLinePeriodRecord
from app.infrastructure.persistence.repositories.sqlalchemy_ingestion_target_repository import (
    SqlAlchemyIngestionTargetRepository,
)
from tests.fixtures.delivery_data import (
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    insert_mapping,
    insert_other_dsp,
    replace_flights,
    seeded_dsp_id,
)

WINDOW = DeliveryDateRange(date(2026, 8, 3), date(2026, 8, 9))
VALIDATED_EARLY = datetime(2026, 7, 20, 9, 0)


@pytest.fixture
def dsp_id(rolled_back_session) -> int:
    return seeded_dsp_id(rolled_back_session)


def _candidates(session, dsp_id: int):
    return SqlAlchemyIngestionTargetRepository(session).find_lines_missing_delivery(dsp_id, WINDOW)


def _mapped_line(session, dsp_id: int, name: str, end: date, start: date = date(2026, 7, 1), status: str = "active",
                 validated_at: datetime | None = VALIDATED_EARLY) -> tuple[int, int]:
    line = insert_campaign_line(session, name, start, end, status)
    insert_mapping(session, line, dsp_id, validated_at=validated_at)
    return line, session.scalars(
        select(CampaignLinePeriodRecord.campaign_period_id).where(CampaignLinePeriodRecord.campaign_line_id == line)
    ).one()


def test_a_mapped_line_with_no_row_in_a_period_that_ended_in_the_window_is_a_candidate(rolled_back_session, dsp_id):
    line, period = _mapped_line(rolled_back_session, dsp_id, "No rows", date(2026, 8, 7))

    assert _candidates(rolled_back_session, dsp_id) == (MissingDeliveryCandidate(line, period),)


def test_a_line_whose_rows_are_all_zero_impressions_is_a_candidate(rolled_back_session, dsp_id):
    line, period = _mapped_line(rolled_back_session, dsp_id, "Zeros", date(2026, 8, 7))
    batch = insert_ingestion_batch(rolled_back_session)
    for day in (3, 4, 5):
        insert_delivery(rolled_back_session, line, date(2026, 8, day), 0, batch)

    assert _candidates(rolled_back_session, dsp_id) == (MissingDeliveryCandidate(line, period),)


def test_a_line_with_impressions_anywhere_in_the_period_is_not_a_candidate(rolled_back_session, dsp_id):
    line, _ = _mapped_line(rolled_back_session, dsp_id, "Delivered", date(2026, 8, 7))
    batch = insert_ingestion_batch(rolled_back_session)
    insert_delivery(rolled_back_session, line, date(2026, 7, 2), 1, batch)  # before the window, still the period

    assert _candidates(rolled_back_session, dsp_id) == ()


def test_delivery_dated_outside_the_period_does_not_count(rolled_back_session, dsp_id):
    line, period = _mapped_line(rolled_back_session, dsp_id, "Late rows", date(2026, 8, 7))
    batch = insert_ingestion_batch(rolled_back_session)
    insert_delivery(rolled_back_session, line, date(2026, 8, 9), 500, batch)

    assert _candidates(rolled_back_session, dsp_id) == (MissingDeliveryCandidate(line, period),)


@pytest.mark.parametrize("last_day, evaluated", [
    (date(2026, 8, 2), False),   # ended before the window
    (date(2026, 8, 3), True),    # first day of the window
    (date(2026, 8, 9), True),    # D-1
    (date(2026, 8, 10), False),  # ends today: D-1 is not past its last day
    (date(2026, 8, 31), False),  # still running
])
def test_only_periods_whose_last_day_is_inside_the_window_are_evaluated(rolled_back_session, dsp_id, last_day, evaluated):
    _mapped_line(rolled_back_session, dsp_id, "Window edge", last_day)

    assert bool(_candidates(rolled_back_session, dsp_id)) is evaluated


@pytest.mark.parametrize("validated_at, evaluated", [
    (datetime(2026, 8, 7, 15, 30), True),   # the same day as the last day of the period
    (datetime(2026, 8, 8, 0, 0), False),    # the day after
    (datetime(2026, 7, 31, 23, 59), True),
])
def test_a_period_that_ended_before_the_mapping_was_validated_is_not_evaluated(
        rolled_back_session, dsp_id, validated_at, evaluated):
    _mapped_line(rolled_back_session, dsp_id, "Mapping date", date(2026, 8, 7), validated_at=validated_at)

    assert bool(_candidates(rolled_back_session, dsp_id)) is evaluated


def test_a_line_whose_mapping_is_not_validated_is_not_evaluated(rolled_back_session, dsp_id):
    _mapped_line(rolled_back_session, dsp_id, "Unvalidated", date(2026, 8, 7), validated_at=None)

    assert _candidates(rolled_back_session, dsp_id) == ()


def test_a_line_with_no_mapping_is_not_evaluated(rolled_back_session, dsp_id):
    insert_campaign_line(rolled_back_session, "Never mapped", date(2026, 7, 1), date(2026, 8, 7))

    assert _candidates(rolled_back_session, dsp_id) == ()


def test_a_mapping_of_another_dsp_does_not_make_the_line_evaluable(rolled_back_session, dsp_id):
    other_dsp = insert_other_dsp(rolled_back_session)
    line = insert_campaign_line(rolled_back_session, "Foreign mapping", date(2026, 7, 1), date(2026, 8, 7))
    insert_mapping(rolled_back_session, line, other_dsp, validated_at=VALIDATED_EARLY)

    assert _candidates(rolled_back_session, dsp_id) == ()


def test_a_line_that_runs_on_another_dsp_is_not_evaluated(rolled_back_session, dsp_id):
    other_dsp = insert_other_dsp(rolled_back_session)
    line = insert_campaign_line(rolled_back_session, "Other DSP", date(2026, 7, 1), date(2026, 8, 7), dsp_id=other_dsp)
    insert_mapping(rolled_back_session, line, other_dsp, validated_at=VALIDATED_EARLY)

    assert _candidates(rolled_back_session, dsp_id) == ()


def test_the_campaign_status_is_not_part_of_the_rule(rolled_back_session, dsp_id):
    line, period = _mapped_line(rolled_back_session, dsp_id, "Switched off", date(2026, 8, 7), status="inactive")

    assert _candidates(rolled_back_session, dsp_id) == (MissingDeliveryCandidate(line, period),)


def test_a_line_with_several_validated_pairs_is_one_candidate(rolled_back_session, dsp_id):
    line, period = _mapped_line(rolled_back_session, dsp_id, "Many pairs", date(2026, 8, 7))
    insert_mapping(rolled_back_session, line, dsp_id, "1001", "2002", validated_at=VALIDATED_EARLY)

    assert _candidates(rolled_back_session, dsp_id) == (MissingDeliveryCandidate(line, period),)


# --- Absence is judged on each flight's own window, not on the whole line or its campaign. ---

def _line_with_flights(session, dsp_id: int, name: str, windows, validated_at: datetime | None = VALIDATED_EARLY,
                       line_item: str = "2001"):
    """A mapped line over July 1 to August 31 whose flights are exactly the windows given."""
    line = insert_campaign_line(session, name, date(2026, 7, 1), date(2026, 8, 31))
    insert_mapping(session, line, dsp_id, external_line_item_id=line_item, validated_at=validated_at)
    return line, replace_flights(session, line, windows)


JULY = (date(2026, 7, 1), date(2026, 7, 31))
AUGUST_TO_7 = (date(2026, 8, 1), date(2026, 8, 7))


def test_a_flight_that_ended_in_the_window_with_only_zero_rows_is_flagged(rolled_back_session, dsp_id):
    line, (august,) = _line_with_flights(rolled_back_session, dsp_id, "Flight zeros", [AUGUST_TO_7])
    batch = insert_ingestion_batch(rolled_back_session)
    for day in (2, 3, 4):
        insert_delivery(rolled_back_session, line, date(2026, 8, day), 0, batch)

    assert _candidates(rolled_back_session, dsp_id) == (MissingDeliveryCandidate(line, august),)


def test_a_flight_with_no_row_at_all_is_flagged(rolled_back_session, dsp_id):
    line, (august,) = _line_with_flights(rolled_back_session, dsp_id, "Flight empty", [AUGUST_TO_7])

    assert _candidates(rolled_back_session, dsp_id) == (MissingDeliveryCandidate(line, august),)


def test_delivery_in_another_flight_of_the_same_line_does_not_count(rolled_back_session, dsp_id):
    line, (_, august) = _line_with_flights(rolled_back_session, dsp_id, "Other flight delivers", [JULY, AUGUST_TO_7])
    insert_delivery(rolled_back_session, line, date(2026, 7, 15), 900, insert_ingestion_batch(rolled_back_session))

    # July delivered but ended before the window; August ended inside it with nothing.
    assert _candidates(rolled_back_session, dsp_id) == (MissingDeliveryCandidate(line, august),)


def test_delivery_inside_the_flight_window_keeps_it_unflagged(rolled_back_session, dsp_id):
    line, _ = _line_with_flights(rolled_back_session, dsp_id, "Flight delivers", [JULY, AUGUST_TO_7])
    insert_delivery(rolled_back_session, line, date(2026, 8, 5), 10, insert_ingestion_batch(rolled_back_session))

    assert _candidates(rolled_back_session, dsp_id) == ()


def test_delivery_after_the_flight_window_does_not_count_for_it(rolled_back_session, dsp_id):
    line, (august,) = _line_with_flights(rolled_back_session, dsp_id, "Delivers after", [AUGUST_TO_7])
    insert_delivery(rolled_back_session, line, date(2026, 8, 8), 500, insert_ingestion_batch(rolled_back_session))

    assert _candidates(rolled_back_session, dsp_id) == (MissingDeliveryCandidate(line, august),)


def test_two_flights_of_one_line_are_judged_one_by_one(rolled_back_session, dsp_id):
    first_half, second_half = (date(2026, 8, 1), date(2026, 8, 4)), (date(2026, 8, 5), date(2026, 8, 8))
    line, (_, second) = _line_with_flights(rolled_back_session, dsp_id, "Two flights", [first_half, second_half])
    insert_delivery(rolled_back_session, line, date(2026, 8, 2), 10, insert_ingestion_batch(rolled_back_session))

    assert _candidates(rolled_back_session, dsp_id) == (MissingDeliveryCandidate(line, second),)


def test_a_mapping_validated_after_a_flight_ended_does_not_make_it_a_candidate(rolled_back_session, dsp_id):
    first_half, second_half = (date(2026, 8, 1), date(2026, 8, 4)), (date(2026, 8, 5), date(2026, 8, 8))
    line, (_, second) = _line_with_flights(
        rolled_back_session, dsp_id, "Mapped mid month", [first_half, second_half], validated_at=datetime(2026, 8, 5, 10, 0)
    )

    # Validated on the 5th: the flight that ended on the 4th is older than the mapping, the one ending on the 8th is not.
    assert _candidates(rolled_back_session, dsp_id) == (MissingDeliveryCandidate(line, second),)


def test_a_flight_still_running_is_not_evaluated_while_an_earlier_one_is(rolled_back_session, dsp_id):
    running = (date(2026, 8, 8), date(2026, 8, 20))
    line, (earlier, _) = _line_with_flights(
        rolled_back_session, dsp_id, "One running", [(date(2026, 8, 1), date(2026, 8, 5)), running]
    )

    assert _candidates(rolled_back_session, dsp_id) == (MissingDeliveryCandidate(line, earlier),)


def test_a_flight_ending_today_or_before_the_window_is_not_evaluated(rolled_back_session, dsp_id):
    _line_with_flights(rolled_back_session, dsp_id, "Ends today", [(date(2026, 8, 5), date(2026, 8, 10))])
    _line_with_flights(rolled_back_session, dsp_id, "Ended before", [(date(2026, 7, 20), date(2026, 8, 2))], line_item="2002")

    assert _candidates(rolled_back_session, dsp_id) == ()
