from dataclasses import replace
from datetime import date, datetime

from app.domain.entities.dsp_mapping import DspMapping, LineDsp
from app.domain.entities.ingestion_exception import ExceptionStatus
from app.domain.exceptions import MappingPairTakenError
from app.domain.repositories.exception_link_repository import ExceptionLinkRepository, LinkableException
from app.domain.value_objects.delivery import ExternalLineKey
from tests.fixtures.in_memory_exception_queue import InMemoryExceptionQueueRepository


class InMemoryExceptionLinkRepository(ExceptionLinkRepository):
    """Writes into scratch copies and publishes them on commit, the way a transaction would."""

    def __init__(self, queue: InMemoryExceptionQueueRepository, line_dsp: dict[int, int],
                 mappings: dict[tuple[int, ExternalLineKey], int] | None = None) -> None:
        self._queue = queue
        self.line_dsp = line_dsp
        self.line_start: dict[int, date] = {}
        self.mappings = dict(mappings or {})  # (dsp, key) -> line
        self.validated: dict[tuple[int, ExternalLineKey], datetime | None] = {}
        self.commits = self.rollbacks = 0
        self.fail_on_resolve = False
        self._snapshot = (dict(self.mappings), dict(queue.summaries))

    def get_exception(self, exception_id: int) -> LinkableException | None:
        summary = self._queue.summaries.get(exception_id)
        if summary is None:
            return None
        key = None if summary.external_campaign_id is None else ExternalLineKey(
            summary.external_campaign_id, summary.external_line_item_id)
        return LinkableException(summary.id, summary.exception_type, summary.status, summary.dsp_id, key)

    def get_line(self, campaign_line_id: int) -> LineDsp | None:
        dsp_id = self.line_dsp.get(campaign_line_id)
        return None if dsp_id is None else LineDsp(dsp_id, f"dsp-{dsp_id}", self.line_start.get(campaign_line_id))

    def pair_exists(self, dsp_id: int, key: ExternalLineKey) -> bool:
        return (dsp_id, key) in self.mappings

    def add_mapping(self, campaign_line_id: int, dsp_id: int, key: ExternalLineKey, validated_at: datetime) -> DspMapping:
        if (dsp_id, key) in self.mappings:
            raise MappingPairTakenError("pair already mapped")
        self.mappings[(dsp_id, key)] = campaign_line_id
        self.validated[(dsp_id, key)] = validated_at
        return DspMapping(len(self.mappings), campaign_line_id, dsp_id, key, validated_at)

    def resolve(self, exception_id: int, resolved_at: datetime, resolved_by: int, note: str) -> bool:
        if self.fail_on_resolve:
            raise RuntimeError("the resolution failed")
        return self._queue.mark_resolved(exception_id, resolved_at, resolved_by, note)

    def commit(self) -> None:
        self.commits += 1
        self._snapshot = (dict(self.mappings), dict(self._queue.summaries))

    def rollback(self) -> None:
        self.rollbacks += 1
        self.mappings, summaries = dict(self._snapshot[0]), dict(self._snapshot[1])
        self._queue.summaries = summaries
