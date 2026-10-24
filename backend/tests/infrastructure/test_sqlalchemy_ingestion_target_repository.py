"""Which lines a run ingests, against real PostgreSQL. Today is 2026-08-10, so the window is Aug 3 to Aug 9."""

from datetime import date

import pytest

from app.domain.value_objects.delivery import DeliveryDateRange, ExternalLineKey
from app.domain.value_objects.ingestion import MappedLine
from app.infrastructure.persistence.repositories.sqlalchemy_ingestion_target_repository import (
    SqlAlchemyIngestionTargetRepository,
)
from tests.fixtures.delivery_data import (
    campaign_id_of,
    insert_campaign_line,
    insert_mapping,
    insert_other_dsp,
    seeded_dsp_id,
)

WINDOW = DeliveryDateRange(date(2026, 8, 3), date(2026, 8, 9))


@pytest.fixture
def dsp_id(rolled_back_session) -> int:
    return seeded_dsp_id(rolled_back_session)


def _targets(session, dsp_id: int):
    return SqlAlchemyIngestionTargetRepository(session).find_targets(dsp_id, WINDOW)


def _line(session, name: str, start: date, end: date, status: str = "active", dsp_id: int | None = None) -> int:
    return insert_campaign_line(session, name, start, end, status, dsp_id)


def test_a_campaign_that_ended_three_days_ago_is_ingested_whatever_its_status(rolled_back_session, dsp_id):
    line = _line(rolled_back_session, "Ended", date(2026, 7, 1), date(2026, 8, 7), status="inactive")
    insert_mapping(rolled_back_session, line, dsp_id)

    targets = _targets(rolled_back_session, dsp_id)

    assert targets.mapped_lines == (MappedLine(line, ExternalLineKey("1001", "2001")),)
    assert targets.unmapped_line_ids == ()


def test_a_campaign_that_starts_tomorrow_is_neither_ingested_nor_skipped(rolled_back_session, dsp_id):
    line = _line(rolled_back_session, "Starts tomorrow", date(2026, 8, 11), date(2026, 8, 31))
    insert_mapping(rolled_back_session, line, dsp_id)
    unmapped = _line(rolled_back_session, "Starts tomorrow without mapping", date(2026, 8, 11), date(2026, 8, 31))

    targets = _targets(rolled_back_session, dsp_id)

    assert (targets.mapped_lines, targets.unmapped_line_ids) == ((), ())
    assert line != unmapped


def test_a_campaign_that_ended_before_the_window_is_neither_ingested_nor_skipped(rolled_back_session, dsp_id):
    line = _line(rolled_back_session, "Long over", date(2026, 7, 1), date(2026, 8, 2))
    insert_mapping(rolled_back_session, line, dsp_id)

    targets = _targets(rolled_back_session, dsp_id)

    assert (targets.mapped_lines, targets.unmapped_line_ids) == ((), ())


@pytest.mark.parametrize("start, end", [
    (date(2026, 7, 1), date(2026, 8, 3)),   # ends on the first day of the window
    (date(2026, 8, 9), date(2026, 8, 20)),  # starts on the last day of the window
])
def test_the_window_bounds_are_inclusive(rolled_back_session, dsp_id, start, end):
    line = _line(rolled_back_session, "Edge", start, end)
    insert_mapping(rolled_back_session, line, dsp_id)

    assert [m.campaign_line_id for m in _targets(rolled_back_session, dsp_id).mapped_lines] == [line]


def test_a_mapping_without_validation_is_skipped_and_counted(rolled_back_session, dsp_id):
    line = _line(rolled_back_session, "Unvalidated", date(2026, 8, 1), date(2026, 8, 31))
    insert_mapping(rolled_back_session, line, dsp_id, validated_at=None)

    targets = _targets(rolled_back_session, dsp_id)

    assert (targets.mapped_lines, targets.unmapped_line_ids) == ((), (line,))


def test_a_line_with_no_mapping_at_all_is_skipped_and_counted(rolled_back_session, dsp_id):
    line = _line(rolled_back_session, "Never mapped", date(2026, 8, 1), date(2026, 8, 31))

    assert _targets(rolled_back_session, dsp_id).unmapped_line_ids == (line,)


def test_a_mapping_of_another_dsp_does_not_make_the_line_ingestable(rolled_back_session, dsp_id):
    other_dsp = insert_other_dsp(rolled_back_session)
    line = _line(rolled_back_session, "Wrong DSP mapping", date(2026, 8, 1), date(2026, 8, 31))
    insert_mapping(rolled_back_session, line, other_dsp)

    targets = _targets(rolled_back_session, dsp_id)

    assert (targets.mapped_lines, targets.unmapped_line_ids) == ((), (line,))


def test_a_line_that_runs_on_another_dsp_is_not_considered_at_all(rolled_back_session, dsp_id):
    other_dsp = insert_other_dsp(rolled_back_session)
    line = _line(rolled_back_session, "Other DSP line", date(2026, 8, 1), date(2026, 8, 31), dsp_id=other_dsp)
    insert_mapping(rolled_back_session, line, other_dsp)
    unmapped = _line(rolled_back_session, "Other DSP unmapped", date(2026, 8, 1), date(2026, 8, 31), dsp_id=other_dsp)

    targets = _targets(rolled_back_session, dsp_id)

    assert (targets.mapped_lines, targets.unmapped_line_ids) == ((), ())
    assert unmapped != line


def test_a_line_with_several_validated_pairs_is_ingested_through_all_of_them(rolled_back_session, dsp_id):
    line = _line(rolled_back_session, "Several pairs", date(2026, 8, 1), date(2026, 8, 31))
    insert_mapping(rolled_back_session, line, dsp_id, "1001", "2001")
    insert_mapping(rolled_back_session, line, dsp_id, "1001", "2002")

    targets = _targets(rolled_back_session, dsp_id)

    assert {m.key for m in targets.mapped_lines} == {ExternalLineKey("1001", "2001"), ExternalLineKey("1001", "2002")}
    assert {m.campaign_line_id for m in targets.mapped_lines} == {line}
    assert targets.unmapped_line_ids == ()


def test_an_unvalidated_pair_beside_a_validated_one_does_not_skip_the_line(rolled_back_session, dsp_id):
    line = _line(rolled_back_session, "Mixed pairs", date(2026, 8, 1), date(2026, 8, 31))
    insert_mapping(rolled_back_session, line, dsp_id, "1001", "2001")
    insert_mapping(rolled_back_session, line, dsp_id, "1001", "2002", validated_at=None)

    targets = _targets(rolled_back_session, dsp_id)

    assert [m.key for m in targets.mapped_lines] == [ExternalLineKey("1001", "2001")]
    assert targets.unmapped_line_ids == ()


def test_the_result_is_ordered_so_runs_are_reproducible(rolled_back_session, dsp_id):
    first = _line(rolled_back_session, "Order one", date(2026, 8, 1), date(2026, 8, 31))
    second = _line(rolled_back_session, "Order two", date(2026, 8, 1), date(2026, 8, 31))
    insert_mapping(rolled_back_session, second, dsp_id, "1001", "2002")
    insert_mapping(rolled_back_session, first, dsp_id, "1001", "2001")

    assert [m.campaign_line_id for m in _targets(rolled_back_session, dsp_id).mapped_lines] == [first, second]


TODAY = date(2026, 8, 10)  # D-1 is Aug 9


def _watched(session) -> tuple[int, ...]:
    return SqlAlchemyIngestionTargetRepository(session).find_watched_campaign_ids(TODAY)


def _campaign(session, line: int) -> int:
    return campaign_id_of(session, line)


def test_an_active_campaign_whose_dates_include_d_minus_1_is_watched(rolled_back_session):
    line = _line(rolled_back_session, "Running", date(2026, 8, 1), date(2026, 8, 31))

    assert _watched(rolled_back_session) == (_campaign(rolled_back_session, line),)


@pytest.mark.parametrize("start, end", [
    (date(2026, 7, 1), date(2026, 8, 9)),   # ends on D-1
    (date(2026, 8, 9), date(2026, 8, 31)),  # starts on D-1
])
def test_d_minus_1_is_inclusive_at_both_ends_of_the_campaign_dates(rolled_back_session, start, end):
    line = _line(rolled_back_session, "Edge", start, end)

    assert _watched(rolled_back_session) == (_campaign(rolled_back_session, line),)


def test_a_campaign_that_ended_three_days_ago_is_not_watched(rolled_back_session):
    _line(rolled_back_session, "Ended", date(2026, 7, 1), date(2026, 8, 7))

    assert _watched(rolled_back_session) == ()


def test_a_campaign_that_starts_tomorrow_is_not_watched(rolled_back_session):
    _line(rolled_back_session, "Starts tomorrow", date(2026, 8, 11), date(2026, 8, 31))

    assert _watched(rolled_back_session) == ()


def test_a_campaign_that_starts_today_has_no_d_minus_1_yet_and_is_not_watched(rolled_back_session):
    _line(rolled_back_session, "Starts today", date(2026, 8, 10), date(2026, 8, 31))

    assert _watched(rolled_back_session) == ()


def test_an_inactive_campaign_is_not_watched_even_inside_its_dates(rolled_back_session):
    _line(rolled_back_session, "Switched off", date(2026, 8, 1), date(2026, 8, 31), status="inactive")

    assert _watched(rolled_back_session) == ()


def test_every_watched_campaign_is_returned_in_id_order(rolled_back_session):
    first = _line(rolled_back_session, "Watched one", date(2026, 8, 1), date(2026, 8, 31))
    second = _line(rolled_back_session, "Watched two", date(2026, 8, 1), date(2026, 8, 31))

    assert _watched(rolled_back_session) == (
        _campaign(rolled_back_session, first),
        _campaign(rolled_back_session, second),
    )
