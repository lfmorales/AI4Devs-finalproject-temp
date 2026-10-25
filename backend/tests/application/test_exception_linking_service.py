"""Linking an exception to a line: one mapping, one resolution, both or neither, with a fixed order of checks."""

from datetime import date, datetime

import pytest

from app.application.services.exception_linking_service import ExceptionLinkingService
from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionSummary, ExceptionType
from app.domain.exceptions import (
    ExceptionNotLinkableError,
    IngestionExceptionAlreadyResolvedError,
    IngestionExceptionNotFoundError,
    LineDspMismatchError,
    LineNotFoundError,
    MappingPairTakenError,
)
from app.domain.value_objects.delivery import ExternalLineKey
from tests.fixtures.in_memory_exception_link import InMemoryExceptionLinkRepository
from tests.fixtures.in_memory_exception_queue import InMemoryExceptionQueueRepository

NOW = datetime(2026, 8, 10, 9, 0)
USER = 7
DSP, OTHER_DSP = 1, 2
LINE = 11
KEY = ExternalLineKey("9", "9")


def _summary(exception_id: int = 1, exception_type=ExceptionType.UNMATCHED_DELIVERY, status=ExceptionStatus.OPEN,
             dsp_id: int | None = DSP, **overrides) -> ExceptionSummary:
    fields = dict(
        id=exception_id, exception_type=exception_type, status=status, ingestion_batch_id=1, dsp_id=dsp_id,
        external_campaign_id="9", external_line_item_id="9", first_date=date(2026, 8, 3), last_date=date(2026, 8, 9),
        days=7, impressions_total=700, clicks_total=21,
    )
    fields.update(overrides)
    return ExceptionSummary(**fields)


def _build(summary: ExceptionSummary | None = None, mappings=None, line_dsp=None):
    queue = InMemoryExceptionQueueRepository([summary or _summary()])
    links = InMemoryExceptionLinkRepository(queue, line_dsp if line_dsp is not None else {LINE: DSP}, mappings)
    return ExceptionLinkingService(links, queue, lambda: NOW), links, queue


def test_linking_creates_a_validated_mapping_for_the_exception_pair_and_resolves_it_with_the_automatic_note():
    service, links, queue = _build()

    result = service.link(1, LINE, USER)

    assert (result.mapping.campaign_line_id, result.mapping.dsp_id, result.mapping.key) == (LINE, DSP, KEY)
    assert result.mapping.validated_at == NOW
    assert links.mappings == {(DSP, KEY): LINE}
    resolved = queue.summaries[1]
    assert (resolved.status, resolved.note, resolved.resolved_by, resolved.resolved_at) == (
        ExceptionStatus.RESOLVED, f"linked to line {LINE}", USER, NOW)
    assert links.commits == 1 and links.rollbacks == 0


def test_the_retained_delivery_is_not_touched():
    service, _, queue = _build()

    result = service.link(1, LINE, USER)

    assert (result.exception.impressions_total, result.exception.days) == (700, 7)


def test_an_unknown_exception_is_not_found():
    service, links, _ = _build()

    with pytest.raises(IngestionExceptionNotFoundError):
        service.link(99, LINE, USER)
    assert links.mappings == {}


def test_an_unknown_line_is_not_found_and_nothing_is_stored():
    service, links, queue = _build()

    with pytest.raises(LineNotFoundError):
        service.link(1, 404, USER)
    assert (links.mappings, queue.summaries[1].status) == ({}, ExceptionStatus.OPEN)


@pytest.mark.parametrize("exception_type", [ExceptionType.MISSING_DELIVERY, ExceptionType.CHANNEL_MISMATCH])
def test_only_an_unmatched_delivery_can_be_linked(exception_type):
    service, links, _ = _build(_summary(exception_type=exception_type, dsp_id=None, external_campaign_id=None,
                                        external_line_item_id=None))

    with pytest.raises(ExceptionNotLinkableError):
        service.link(1, LINE, USER)
    assert links.mappings == {}


def test_a_resolved_exception_cannot_be_linked():
    service, links, _ = _build(_summary(status=ExceptionStatus.RESOLVED, resolved_at=NOW, resolved_by=USER))

    with pytest.raises(IngestionExceptionAlreadyResolvedError):
        service.link(1, LINE, USER)
    assert links.mappings == {}


def test_a_pair_that_is_already_mapped_is_refused_and_the_exception_stays_open():
    service, links, queue = _build(mappings={(DSP, KEY): 12})

    with pytest.raises(MappingPairTakenError):
        service.link(1, LINE, USER)
    assert queue.summaries[1].status is ExceptionStatus.OPEN
    assert links.mappings == {(DSP, KEY): 12}


def test_a_line_of_another_dsp_is_refused():
    service, links, _ = _build(line_dsp={LINE: OTHER_DSP})

    with pytest.raises(LineDspMismatchError):
        service.link(1, LINE, USER)
    assert links.mappings == {}


def test_not_linkable_is_reported_before_already_resolved_and_before_an_unknown_line():
    service, _, _ = _build(_summary(exception_type=ExceptionType.MISSING_DELIVERY, status=ExceptionStatus.RESOLVED,
                                    dsp_id=None, external_campaign_id=None, external_line_item_id=None))

    with pytest.raises(ExceptionNotLinkableError):
        service.link(1, 404, USER)


def test_a_failure_while_resolving_rolls_the_mapping_back():
    service, links, queue = _build()
    links.fail_on_resolve = True

    with pytest.raises(RuntimeError):
        service.link(1, LINE, USER)

    assert links.mappings == {}
    assert queue.summaries[1].status is ExceptionStatus.OPEN
    assert (links.commits, links.rollbacks) == (0, 1)


def test_an_exception_resolved_by_someone_else_in_the_meantime_rolls_the_mapping_back():
    service, links, queue = _build()
    original = links.resolve

    def resolved_elsewhere(*args, **kwargs):
        queue.mark_resolved(1, NOW, 99, "by someone else")
        return original(*args, **kwargs)  # now reports False: the conditional update marks nothing

    links.resolve = resolved_elsewhere

    with pytest.raises(IngestionExceptionAlreadyResolvedError):
        service.link(1, LINE, USER)
    assert links.mappings == {}
