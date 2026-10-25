from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.entities.dsp_mapping import DspMapping, LineDsp
from app.domain.value_objects.delivery import ExternalLineKey


class DspMappingRepository(ABC):
    @abstractmethod
    def get_line_dsp(self, campaign_line_id: int) -> LineDsp | None:
        """The DSP of a campaign line, or None when the line does not exist."""

    @abstractmethod
    def pair_exists(self, dsp_id: int, key: ExternalLineKey) -> bool:
        """Whether the pair is already mapped to a campaign line of the DSP."""

    @abstractmethod
    def add(
        self, campaign_line_id: int, dsp_id: int, key: ExternalLineKey, validated_at: datetime | None
    ) -> DspMapping:
        """Store a mapping; raises DuplicateDspMappingError if the pair was mapped in the meantime."""
