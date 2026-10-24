"""Which lines the absence check evaluates, against PostgreSQL. Today is 2026-08-10, so the window is Aug 3 to Aug 9."""

from datetime import date, datetime

import pytest

from app.domain.value_objects.delivery import DeliveryDateRange
from app.domain.value_objects.ingestion import MissingDeliveryCandidate
from app.infrastructure.persistence.models.campaign import CampaignLineRecord
from app.infrastructure.persistence.repositories.sqlalchemy_ingestion_target_repository import (
    SqlAlchemyIngestionTargetRepository,
)
from tests.fixtures.delivery_data import (
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    insert_mapping,
    insert_other_dsp,
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
    return line, session.get(CampaignLineRecord, line).campaign_period_id


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
