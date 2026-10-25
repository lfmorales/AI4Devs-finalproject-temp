"""The absence check as a service method: one exception per line and period, however often it runs."""

from datetime import date

from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionType
from app.domain.value_objects.delivery import DeliveryDateRange
from app.domain.value_objects.ingestion import IngestionTargets, MissingDeliveryCandidate
from tests.fixtures.ingestion_harness import DSP_ID, IngestionHarness

TODAY = date(2026, 8, 10)
BATCH = 1


def _harness(candidates: list[MissingDeliveryCandidate]) -> IngestionHarness:
    harness = IngestionHarness()
    harness.targets.missing_candidates = tuple(candidates)
    return harness


def test_it_asks_for_periods_that_ended_inside_the_ingestion_window():
    harness = _harness([])

    harness.service.detect_missing_delivery(DSP_ID, TODAY, BATCH)

    assert harness.targets.missing_requests == [(DSP_ID, DeliveryDateRange(date(2026, 8, 3), date(2026, 8, 9)))]


def test_each_candidate_becomes_an_open_missing_delivery_exception():
    harness = _harness([MissingDeliveryCandidate(11, 101), MissingDeliveryCandidate(12, 102)])

    created = harness.service.detect_missing_delivery(DSP_ID, TODAY, BATCH)

    exceptions = sorted(harness.exceptions.exceptions.values(), key=lambda e: e.campaign_line_id)
    assert created == 2
    assert [(e.exception_type, e.status, e.campaign_line_id, e.campaign_period_id, e.ingestion_batch_id)
            for e in exceptions] == [
        (ExceptionType.MISSING_DELIVERY, ExceptionStatus.OPEN, 11, 101, BATCH),
        (ExceptionType.MISSING_DELIVERY, ExceptionStatus.OPEN, 12, 102, BATCH),
    ]


def test_evaluating_twice_creates_no_second_exception():
    harness = _harness([MissingDeliveryCandidate(11, 101)])

    first = harness.service.detect_missing_delivery(DSP_ID, TODAY, BATCH)
    second = harness.service.detect_missing_delivery(DSP_ID, TODAY, 2)

    assert (first, second, len(harness.exceptions.exceptions)) == (1, 0, 1)


def test_no_candidates_creates_nothing():
    harness = _harness([])

    assert harness.service.detect_missing_delivery(DSP_ID, TODAY, BATCH) == 0
    assert harness.exceptions.exceptions == {}


def test_it_does_not_call_the_dsp():
    harness = _harness([MissingDeliveryCandidate(11, 101)])

    harness.service.detect_missing_delivery(DSP_ID, TODAY, BATCH)

    assert harness.client.requested_ranges == []


def test_the_window_follows_the_configured_length():
    harness = IngestionHarness(window_days=3)

    harness.service.detect_missing_delivery(DSP_ID, TODAY, BATCH)

    assert harness.targets.missing_requests == [(DSP_ID, DeliveryDateRange(date(2026, 8, 7), date(2026, 8, 9)))]
