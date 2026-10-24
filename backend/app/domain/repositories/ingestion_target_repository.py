from abc import ABC, abstractmethod

from app.domain.value_objects.delivery import DeliveryDateRange
from app.domain.value_objects.ingestion import IngestionTargets


class IngestionTargetRepository(ABC):
    @abstractmethod
    def find_targets(self, dsp_id: int, window: DeliveryDateRange) -> IngestionTargets:
        """The active lines of the DSP over the window, split into those with a validated mapping and those without."""
