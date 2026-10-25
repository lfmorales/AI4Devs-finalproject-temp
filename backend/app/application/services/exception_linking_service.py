from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from app.domain.entities.dsp_mapping import DspMapping
from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionSummary, ExceptionType
from app.domain.exceptions import (
    ExceptionNotLinkableError,
    IngestionExceptionAlreadyResolvedError,
    IngestionExceptionNotFoundError,
    LineDspMismatchError,
    LineNotFoundError,
    MappingPairTakenError,
)
from app.domain.repositories.exception_link_repository import ExceptionLinkRepository
from app.domain.repositories.exception_queue_repository import ExceptionQueueRepository
from app.domain.value_objects.ingestion import needs_history_load


@dataclass(frozen=True)
class LinkResult:
    mapping: DspMapping
    exception: ExceptionSummary
    # The line started before the normal window, so its earlier delivery is not loaded by itself.
    needs_history_load: bool = False


class ExceptionLinkingService:
    """Maps the pair of an unmatched-delivery exception to a campaign line and resolves the exception, or neither.

    The mapping is validated without asking the DSP: the exception is the proof that the pair exists there. The
    retained delivery is not moved; the next ingestion window brings it in through the new mapping.
    """

    def __init__(
        self,
        links: ExceptionLinkRepository,
        queue: ExceptionQueueRepository,
        clock: Callable[[], datetime],
        today: Callable[[], date] | None = None,
    ) -> None:
        self._links = links
        self._queue = queue
        self._clock = clock
        self._today = today

    def link(self, exception_id: int, campaign_line_id: int, linked_by: int) -> LinkResult:
        try:
            mapping, line_start = self._link(exception_id, campaign_line_id, linked_by)
        except BaseException:
            self._links.rollback()
            raise
        self._links.commit()
        summary = self._queue.get_summary(exception_id)
        assert summary is not None
        history = (
            self._today is not None and line_start is not None and needs_history_load(line_start, self._today())
        )
        return LinkResult(mapping, summary, history)

    def _link(self, exception_id: int, campaign_line_id: int, linked_by: int) -> tuple[DspMapping, date | None]:
        exception = self._links.get_exception(exception_id)
        if exception is None:
            raise IngestionExceptionNotFoundError(f"exception {exception_id} does not exist")
        if exception.exception_type is not ExceptionType.UNMATCHED_DELIVERY or exception.key is None \
                or exception.dsp_id is None:
            raise ExceptionNotLinkableError(f"exception {exception_id} is not an unmatched delivery")
        if exception.status is ExceptionStatus.RESOLVED:
            raise IngestionExceptionAlreadyResolvedError(f"exception {exception_id} is already resolved")
        line = self._links.get_line(campaign_line_id)
        if line is None:
            raise LineNotFoundError(f"campaign line {campaign_line_id} does not exist")
        if line.dsp_id != exception.dsp_id:
            raise LineDspMismatchError(f"campaign line {campaign_line_id} runs on another DSP")
        if self._links.pair_exists(exception.dsp_id, exception.key):
            raise MappingPairTakenError("pair already mapped")

        now = self._clock()
        mapping = self._links.add_mapping(campaign_line_id, exception.dsp_id, exception.key, now)
        # The conditional update decides when two operators work the same exception at once.
        if not self._links.resolve(exception_id, now, linked_by, f"linked to line {campaign_line_id}"):
            raise IngestionExceptionAlreadyResolvedError(f"exception {exception_id} is already resolved")
        return mapping, line.line_start_date
