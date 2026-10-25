"""Unmatched delivery with something in it becomes one exception per DSP and pair, with its figures kept per date."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.domain.entities.ingestion_batch import IngestionRoute
from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionType, IngestionException
from app.domain.value_objects.delivery import ExternalLineKey
from app.domain.value_objects.ingestion import MappedLine
from tests.fixtures.delivery_rows import daily_delivery, dsp_row
from tests.fixtures.in_memory_delivery_repository import InMemoryDeliveryRepository
from tests.fixtures.ingestion_harness import DSP_ID, IngestionHarness

TODAY = date(2026, 8, 10)
LINE = 11
MAPPED = ExternalLineKey("100", "200")
STRANGER = ExternalLineKey("9", "9")
OTHER_STRANGER = ExternalLineKey("9", "10")
D5, D6, D7 = date(2026, 8, 5), date(2026, 8, 6), date(2026, 8, 7)


def _harness(rows, existing=()):
    return IngestionHarness(rows=rows, mapped_lines=[MappedLine(LINE, MAPPED)], existing=existing)


def _only_exception(harness: IngestionHarness) -> IngestionException:
    assert len(harness.exceptions.exceptions) == 1
    return next(iter(harness.exceptions.exceptions.values()))


def _retained(harness: IngestionHarness, exception: IngestionException):
    return {day: row for (exception_id, day), row in harness.exceptions.retained.items() if exception_id == exception.id}


def test_unmatched_delivery_with_impressions_is_recorded_with_its_dsp_pair_and_batch():
    harness = _harness([dsp_row(D5, STRANGER, impressions=40)])

    result = harness.service.run(DSP_ID, TODAY)

    exception = _only_exception(harness)
    assert (exception.exception_type, exception.status, exception.dsp_id, exception.key) == (
        ExceptionType.UNMATCHED_DELIVERY, ExceptionStatus.OPEN, DSP_ID, STRANGER)
    assert exception.ingestion_batch_id == result.batch_id


def test_the_delivery_figures_are_retained_for_the_date():
    row = dsp_row(D5, STRANGER, impressions=40, clicks=2, media_cost=Decimal("1.234567"),
                  measurable_impressions=30, viewable_impressions=20)
    harness = _harness([row])

    harness.service.run(DSP_ID, TODAY)

    retained = _retained(harness, _only_exception(harness))[D5]
    assert (retained.impressions, retained.clicks, retained.media_cost) == (40, 2, Decimal("1.234567"))
    assert (retained.measurable_impressions, retained.viewable_impressions) == (30, 20)


def test_the_first_and_last_dates_span_the_retained_delivery():
    harness = _harness([dsp_row(D7, STRANGER), dsp_row(D5, STRANGER), dsp_row(D6, STRANGER)])

    harness.service.run(DSP_ID, TODAY)

    exception = _only_exception(harness)
    assert (exception.first_date, exception.last_date) == (D5, D7)


def test_several_unmatched_rows_of_one_pair_and_date_are_summed():
    harness = _harness([dsp_row(D5, STRANGER, impressions=40, clicks=1, media_cost=Decimal("1.5")),
                        dsp_row(D5, STRANGER, impressions=10, clicks=2, media_cost=Decimal("0.25"))])

    harness.service.run(DSP_ID, TODAY)

    retained = _retained(harness, _only_exception(harness))
    assert len(retained) == 1
    assert (retained[D5].impressions, retained[D5].clicks, retained[D5].media_cost) == (50, 3, Decimal("1.75"))


def test_different_pairs_get_different_exceptions():
    harness = _harness([dsp_row(D5, STRANGER), dsp_row(D5, OTHER_STRANGER)])

    harness.service.run(DSP_ID, TODAY)

    assert {e.key for e in harness.exceptions.exceptions.values()} == {STRANGER, OTHER_STRANGER}


def test_an_unmatched_row_of_zeros_is_counted_and_not_recorded():
    harness = _harness([dsp_row(D5, STRANGER, impressions=0, media_cost=Decimal("0"))])

    result = harness.service.run(DSP_ID, TODAY)

    assert harness.exceptions.exceptions == {}
    assert result.zero_unmatched_row_count == 1


@pytest.mark.parametrize("impressions, cost", [(0, Decimal("0.01")), (1, Decimal("0"))])
def test_an_unmatched_row_with_impressions_or_cost_is_recorded(impressions, cost):
    harness = _harness([dsp_row(D5, STRANGER, impressions=impressions, media_cost=cost)])

    result = harness.service.run(DSP_ID, TODAY)

    assert len(harness.exceptions.exceptions) == 1
    assert result.zero_unmatched_row_count == 0


def test_matched_rows_are_still_stored_beside_unmatched_ones():
    harness = _harness([dsp_row(D5, MAPPED, impressions=700), dsp_row(D5, STRANGER, impressions=40)])

    result = harness.service.run(DSP_ID, TODAY)

    assert harness.deliveries.impressions_by_line_and_day() == {(LINE, D5): 700}
    assert (result.stored_row_count, len(harness.exceptions.exceptions)) == (1, 1)


def test_the_upload_route_records_the_same_exceptions():
    harness = _harness([dsp_row(D5, STRANGER, impressions=40)])

    harness.service.run(DSP_ID, TODAY, route=IngestionRoute.UPLOAD, source_file="export.xlsx")

    assert _only_exception(harness).key == STRANGER


def test_running_the_same_window_twice_keeps_one_exception_and_one_row_per_date():
    harness = _harness([dsp_row(D5, STRANGER, impressions=40), dsp_row(D6, STRANGER, impressions=50)])

    harness.service.run(DSP_ID, TODAY)
    harness.service.run(DSP_ID, TODAY)

    exception = _only_exception(harness)
    assert sorted(_retained(harness, exception)) == [D5, D6]


def test_a_second_run_replaces_the_retained_figures_of_its_dates_and_keeps_the_first_batch():
    harness = _harness([dsp_row(D5, STRANGER, impressions=40)])
    first = harness.service.run(DSP_ID, TODAY)
    harness.client._rows = [dsp_row(D5, STRANGER, impressions=99)]

    second = harness.service.run(DSP_ID, TODAY)

    exception = _only_exception(harness)
    assert _retained(harness, exception)[D5].impressions == 99
    assert exception.ingestion_batch_id == first.batch_id != second.batch_id


def test_retained_delivery_outside_the_window_is_left_alone():
    harness = _harness([dsp_row(D5, STRANGER, impressions=40)])
    harness.service.run(DSP_ID, TODAY)
    older = date(2026, 7, 20)
    exception = _only_exception(harness)
    harness.exceptions.retained[(exception.id, older)] = harness.exceptions.retained[(exception.id, D5)]

    harness.service.run(DSP_ID, TODAY)

    assert older in _retained(harness, exception)


def test_a_restatement_that_drops_a_date_removes_its_row_and_narrows_the_span():
    harness = _harness([dsp_row(D5, STRANGER), dsp_row(D7, STRANGER)])
    harness.service.run(DSP_ID, TODAY)
    harness.client._rows = [dsp_row(D5, STRANGER)]

    harness.service.run(DSP_ID, TODAY)

    exception = _only_exception(harness)
    assert (sorted(_retained(harness, exception)), exception.last_date) == ([D5], D5)


def test_a_resolved_pair_that_delivers_again_is_not_reopened_and_its_new_delivery_is_kept():
    harness = _harness([dsp_row(D5, STRANGER, impressions=40)])
    harness.exceptions.seed(IngestionException(
        id=1, exception_type=ExceptionType.UNMATCHED_DELIVERY, status=ExceptionStatus.RESOLVED,
        ingestion_batch_id=1, dsp_id=DSP_ID, key=STRANGER, resolved_at=datetime(2026, 8, 8, 9, 0), resolved_by=7,
        note="Typo in the DSP name"))

    harness.service.run(DSP_ID, TODAY)

    exception = _only_exception(harness)
    assert (exception.status, exception.resolved_by, exception.note) == (ExceptionStatus.RESOLVED, 7, "Typo in the DSP name")
    assert _retained(harness, exception)[D5].impressions == 40


def test_the_same_pair_is_a_separate_exception_for_another_dsp():
    harness = _harness([dsp_row(D5, STRANGER, impressions=40)])
    harness.exceptions.seed(IngestionException(
        id=1, exception_type=ExceptionType.UNMATCHED_DELIVERY, status=ExceptionStatus.OPEN,
        ingestion_batch_id=1, dsp_id=DSP_ID + 1, key=STRANGER))

    harness.service.run(DSP_ID, TODAY)

    assert sorted(e.dsp_id for e in harness.exceptions.exceptions.values()) == [DSP_ID, DSP_ID + 1]


def test_a_failure_while_recording_rolls_back_the_deliveries_and_the_exceptions():
    previous = daily_delivery(LINE, D5, impressions=1000)
    harness = _harness([dsp_row(D5, MAPPED, impressions=700), dsp_row(D5, STRANGER, impressions=40)],
                       existing=[previous])

    def failing_add(exception_id, rows):
        list(rows)
        raise RuntimeError("storing the retained delivery failed")

    harness.exceptions.add_retained = failing_add

    with pytest.raises(RuntimeError):
        harness.service.run(DSP_ID, TODAY)

    assert harness.deliveries.rows == {(LINE, D5): previous}
    assert harness.exceptions.exceptions == {}
