from datetime import datetime

from app.domain.entities.dsp_mapping import DspMapping, LineDsp
from app.domain.exceptions import DuplicateDspMappingError
from app.domain.repositories.dsp_mapping_repository import DspMappingRepository
from app.domain.value_objects.delivery import ExternalLineKey


class InMemoryDspMappingRepository(DspMappingRepository):
    def __init__(self, lines: dict[int, LineDsp]) -> None:
        self._lines = lines
        self.mappings: list[DspMapping] = []

    def get_line_dsp(self, campaign_line_id: int) -> LineDsp | None:
        return self._lines.get(campaign_line_id)

    def pair_exists(self, dsp_id: int, key: ExternalLineKey) -> bool:
        return any(m.dsp_id == dsp_id and m.key == key for m in self.mappings)

    def add(
        self, campaign_line_id: int, dsp_id: int, key: ExternalLineKey, validated_at: datetime | None
    ) -> DspMapping:
        if self.pair_exists(dsp_id, key):
            raise DuplicateDspMappingError("pair already mapped")
        mapping = DspMapping(len(self.mappings) + 1, campaign_line_id, dsp_id, key, validated_at)
        self.mappings.append(mapping)
        return mapping
