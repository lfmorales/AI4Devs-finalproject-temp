from abc import ABC, abstractmethod
from datetime import date

from app.domain.value_objects.delivery import DeliveryDateRange
from app.domain.value_objects.ingestion import IngestionTargets


class IngestionTargetRepository(ABC):
    @abstractmethod
    def find_targets(self, dsp_id: int, window: DeliveryDateRange) -> IngestionTargets:
        """The active lines of the DSP over the window, split into those with a validated mapping and those without."""

    @abstractmethod
    def find_watched_campaign_ids(self, today: date) -> tuple[int, ...]:
        """The campaigns whose missing D-1 delivery is worth a flag: status active, with D-1 inside their dates."""
