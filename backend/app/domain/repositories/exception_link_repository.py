from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.domain.entities.dsp_mapping import DspMapping
from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionType
from app.domain.value_objects.delivery import ExternalLineKey


@dataclass(frozen=True)
class LinkableException:
    """What linking needs to know about an exception: its kind, whether it is open and the pair it carries."""

    id: int
    exception_type: ExceptionType
    status: ExceptionStatus
    dsp_id: int | None
    key: ExternalLineKey | None


class ExceptionLinkRepository(ABC):
    """The writes of linking, which share one transaction: nothing commits until `commit` is called."""

    @abstractmethod
    def get_exception(self, exception_id: int) -> LinkableException | None: ...

    @abstractmethod
    def get_line_dsp_id(self, campaign_line_id: int) -> int | None:
        """The DSP the campaign line runs on, or None when the line does not exist."""

    @abstractmethod
    def pair_exists(self, dsp_id: int, key: ExternalLineKey) -> bool: ...

    @abstractmethod
    def add_mapping(
        self, campaign_line_id: int, dsp_id: int, key: ExternalLineKey, validated_at: datetime
    ) -> DspMapping:
        """Store a validated mapping without committing; MappingPairTakenError if the pair was taken meanwhile."""

    @abstractmethod
    def resolve(self, exception_id: int, resolved_at: datetime, resolved_by: int, note: str) -> bool:
        """Mark an open exception resolved without committing; False when it was no longer open."""

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...
