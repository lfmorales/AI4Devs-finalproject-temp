"""The absence check as a service method: one exception per line and period, however often it runs."""

from datetime import date, datetime

from app.domain.entities.ingestion_batch import IngestionRoute
from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionType
from app.domain.value_objects.delivery import DeliveryDateRange
from app.domain.value_objects.ingestion import IngestionTargets, MissingDeliveryCandidate
from app.infrastructure.dsp.equativ_delivery_client import EquativDeliveryClient
from tests.fixtures.fake_equativ import REPORT_ID, FakeEquativ
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


EQUATIV_DSP_ID = 3
EQUATIV_TODAY = date(2026, 11, 18)


def test_an_equativ_absence_is_recorded_with_the_equativ_batch() -> None:
    fake = FakeEquativ(rows=[])
    harness = IngestionHarness(
        client=EquativDeliveryClient(
            "synthetic-equativ-client-id", "synthetic-equativ-client-secret", fake.client(),
            sleep=lambda _: None, monotonic=lambda: 0.0,
        )
    )
    harness.targets.missing_candidates = (MissingDeliveryCandidate(21, 201),)
    # An Adform batch of the same night comes first, so the Equativ batch is not merely the first one.
    window = DeliveryDateRange(date(2026, 11, 11), date(2026, 11, 17))
    adform_batch = harness.batches.start(DSP_ID, IngestionRoute.API, None, datetime(2026, 11, 18, 2, 0), window)
    equativ_batch = harness.service.run(EQUATIV_DSP_ID, EQUATIV_TODAY).batch_id

    created = harness.service.detect_missing_delivery(EQUATIV_DSP_ID, EQUATIV_TODAY, equativ_batch)

    [exception] = harness.exceptions.exceptions.values()
    assert created == 1
    assert equativ_batch != adform_batch
    assert (exception.exception_type, exception.campaign_line_id, exception.campaign_period_id,
            exception.ingestion_batch_id) == (ExceptionType.MISSING_DELIVERY, 21, 201, equativ_batch)
    assert harness.batches.records[equativ_batch].dsp_id == EQUATIV_DSP_ID
    assert harness.batches.records[equativ_batch].source_file == REPORT_ID
    assert harness.targets.missing_requests == [(EQUATIV_DSP_ID, window)]
