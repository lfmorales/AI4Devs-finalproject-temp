"""Reading the queue and resolving an exception, which only marks it."""

from datetime import date, datetime

import pytest

from app.application.services.ingestion_exception_service import IngestionExceptionService
from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionSummary, ExceptionType
from app.domain.exceptions import IngestionExceptionAlreadyResolvedError, IngestionExceptionNotFoundError
from tests.fixtures.in_memory_exception_queue import InMemoryExceptionQueueRepository

NOW = datetime(2026, 8, 10, 9, 0)
USER = 7


def _summary(exception_id: int, status: ExceptionStatus = ExceptionStatus.OPEN, **overrides) -> ExceptionSummary:
    fields = dict(
        id=exception_id, exception_type=ExceptionType.UNMATCHED_DELIVERY, status=status, ingestion_batch_id=1,
        dsp_id=1, external_campaign_id="9", external_line_item_id="9", first_date=date(2026, 8, 3),
        last_date=date(2026, 8, 9), days=7, impressions_total=700, clicks_total=21,
    )
    fields.update(overrides)
    return ExceptionSummary(**fields)


def _service(summaries):
    repository = InMemoryExceptionQueueRepository(summaries)
    return IngestionExceptionService(repository, lambda: NOW), repository


def test_listing_without_a_status_returns_everything_in_id_order():
    service, _ = _service([_summary(2), _summary(1, ExceptionStatus.RESOLVED, resolved_at=NOW, resolved_by=USER)])

    assert [s.id for s in service.list_exceptions(None)] == [1, 2]


@pytest.mark.parametrize("status", [ExceptionStatus.OPEN, ExceptionStatus.RESOLVED])
def test_listing_by_status_returns_only_that_status(status):
    service, _ = _service([_summary(1), _summary(2, ExceptionStatus.RESOLVED, resolved_at=NOW, resolved_by=USER)])

    assert {s.status for s in service.list_exceptions(status)} == {status}


def test_resolving_marks_the_time_the_user_and_the_note():
    service, repository = _service([_summary(1)])

    resolved = service.resolve(1, USER, "Typo in the DSP name")

    assert (resolved.status, resolved.resolved_at, resolved.resolved_by, resolved.note) == (
        ExceptionStatus.RESOLVED, NOW, USER, "Typo in the DSP name")
    assert repository.summaries[1] == resolved


def test_the_note_is_optional():
    service, _ = _service([_summary(1)])

    assert service.resolve(1, USER, None).note is None


def test_a_resolved_exception_leaves_the_open_queue_and_stays_readable():
    service, _ = _service([_summary(1), _summary(2)])

    service.resolve(1, USER, None)

    assert [s.id for s in service.list_exceptions(ExceptionStatus.OPEN)] == [2]
    assert [s.id for s in service.list_exceptions(ExceptionStatus.RESOLVED)] == [1]


def test_resolving_changes_nothing_but_the_resolution_fields():
    service, repository = _service([_summary(1)])
    before = repository.summaries[1]

    after = service.resolve(1, USER, "ok")

    assert (after.days, after.impressions_total, after.clicks_total, after.first_date, after.last_date) == (
        before.days, before.impressions_total, before.clicks_total, before.first_date, before.last_date)


def test_resolving_an_exception_twice_is_a_conflict_and_keeps_the_first_resolution():
    service, repository = _service([_summary(1)])
    service.resolve(1, USER, "first")

    with pytest.raises(IngestionExceptionAlreadyResolvedError):
        service.resolve(1, 99, "second")

    assert (repository.summaries[1].resolved_by, repository.summaries[1].note) == (USER, "first")


def test_resolving_an_exception_that_does_not_exist_is_not_found():
    service, _ = _service([])

    with pytest.raises(IngestionExceptionNotFoundError):
        service.resolve(404, USER, None)
