"""run_ingestion --from/--to: one request for a custom range, the same service, no absence detection."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select

from app.domain.value_objects.delivery import DeliveryDateRange
from app.infrastructure.persistence.models.delivery import (
    DailyDeliveryRecord,
    IngestionBatchRecord,
    IngestionExceptionRecord,
)
from scripts.run_ingestion import main
from tests.scripts.test_run_ingestion import FailsAfterTwoRows, Scenario

# 12:00 UTC on 10 August is the 10th in Madrid, so the last day a range may end on is the 9th.
NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def scenario(rolled_back_session, test_engine):
    return Scenario(rolled_back_session, test_engine)


def _range(scenario: Scenario, *arguments: str, now: datetime = NOW, client=None) -> int:
    return main(
        list(arguments), out=scenario.output.append, engine=scenario.engine,
        session_factory=lambda: scenario.session, client=client or scenario.client, now=lambda: now,
    )


def _window(start: str, end: str) -> list[str]:
    return ["--from", start, "--to", end]


def test_one_request_asks_for_the_whole_range(scenario):
    assert _range(scenario, *_window("2026-08-03", "2026-08-09")) == 0

    assert scenario.client.requested_ranges == [DeliveryDateRange(date(2026, 8, 3), date(2026, 8, 9))]


def test_the_batch_records_the_range(scenario):
    _range(scenario, *_window("2026-08-03", "2026-08-09"))

    batch = scenario.session.scalars(select(IngestionBatchRecord)).one()
    assert (batch.window_start, batch.window_end, batch.status) == (date(2026, 8, 3), date(2026, 8, 9), "succeeded")


def test_it_stores_the_delivery_of_the_range_with_the_same_service(scenario):
    _range(scenario, *_window("2026-08-03", "2026-08-09"))

    assert scenario.count(DailyDeliveryRecord) == 2
    assert scenario.session.scalar(select(func.sum(DailyDeliveryRecord.impressions))) == 1000


def test_only_the_lines_whose_dates_overlap_the_range_are_ingested(scenario):
    _range(scenario, *_window("2026-07-01", "2026-07-20"))

    assert "mapped_lines: 0" in scenario.output
    assert scenario.count(DailyDeliveryRecord) == 0

    scenario.output.clear()
    _range(scenario, *_window("2026-07-25", "2026-08-02"))

    assert "mapped_lines: 2" in scenario.output


def test_absence_is_not_detected_with_a_custom_range_and_the_output_says_so(scenario):
    assert _range(scenario, *_window("2026-08-03", "2026-08-09")) == 0

    assert "absences: skipped, custom range" in scenario.output
    assert not any(line.startswith("absences: ") and line != "absences: skipped, custom range" for line in scenario.output)
    assert scenario.session.scalar(
        select(func.count()).select_from(IngestionExceptionRecord).where(IngestionExceptionRecord.exception_type == "missing_delivery")
    ) == 0


def test_the_normal_run_still_detects_absence(scenario):
    assert scenario.run() == 0

    assert "absences: 1" in scenario.output


def test_repeating_a_range_changes_no_row_and_no_exception(scenario):
    assert _range(scenario, *_window("2026-08-03", "2026-08-09")) == 0
    first = (scenario.count(DailyDeliveryRecord), scenario.count(IngestionExceptionRecord))
    totals = scenario.session.scalar(select(func.sum(DailyDeliveryRecord.impressions)))

    assert _range(scenario, *_window("2026-08-03", "2026-08-09")) == 0

    assert (scenario.count(DailyDeliveryRecord), scenario.count(IngestionExceptionRecord)) == first
    assert scenario.session.scalar(select(func.sum(DailyDeliveryRecord.impressions))) == totals
    assert scenario.batch_statuses() == ["succeeded", "succeeded"]


def test_thirty_one_days_are_accepted_and_thirty_two_are_not(scenario):
    later = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)

    assert _range(scenario, *_window("2026-08-01", "2026-08-31"), now=later) == 0
    scenario.output.clear()

    assert _range(scenario, *_window("2026-07-31", "2026-08-31"), now=later) == 3
    assert scenario.output == ["status: not configured"]
    assert len(scenario.client.requested_ranges) == 1


def test_the_range_may_end_the_day_before_today_but_not_today(scenario):
    assert _range(scenario, *_window("2026-08-08", "2026-08-09")) == 0

    requested = len(scenario.client.requested_ranges)
    assert _range(scenario, *_window("2026-08-08", "2026-08-10")) == 3
    assert len(scenario.client.requested_ranges) == requested


def test_the_zone_decides_which_day_is_today(scenario):
    # 23:30 UTC on the 9th is already the 10th in Madrid, so the 9th is the last day allowed...
    assert _range(scenario, *_window("2026-08-08", "2026-08-09"), now=datetime(2026, 8, 9, 23, 30, tzinfo=UTC)) == 0
    # ...and at 21:30 UTC on the 9th it is still the 9th there, so the 9th is not over yet.
    assert _range(scenario, *_window("2026-08-08", "2026-08-09"), now=datetime(2026, 8, 9, 21, 30, tzinfo=UTC)) == 3


@pytest.mark.parametrize("arguments", [
    ["--from", "2026-08-03"],
    ["--to", "2026-08-09"],
    ["--from", "2026-08-09", "--to", "2026-08-03"],
    ["--from", "2026-08-03", "--to", "2026-08-09", "--date", "2026-08-10"],
    ["--from", "2026/08/03", "--to", "2026-08-09"],
    ["--from", "2026-08-03", "--to", "yesterday"],
])
def test_invalid_range_arguments_exit_3_without_a_request_or_a_batch(scenario, arguments):
    assert _range(scenario, *arguments) == 3

    assert scenario.output == ["status: not configured"]
    assert scenario.client.requested_ranges == []
    assert scenario.batch_statuses() == []


def test_a_single_day_range_is_valid(scenario):
    assert _range(scenario, *_window("2026-08-05", "2026-08-05")) == 0


def test_a_failed_range_leaves_a_failed_batch_and_no_partial_delivery(rolled_back_session, test_engine):
    failing = Scenario(rolled_back_session, test_engine, client_class=FailsAfterTwoRows)

    assert _range(failing, *_window("2026-08-03", "2026-08-09")) == 1

    assert failing.batch_statuses() == ["failed"]
    assert failing.count(DailyDeliveryRecord) == 0
