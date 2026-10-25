from abc import ABC, abstractmethod
from datetime import date

from app.domain.value_objects.delivery import DeliveryDateRange
from app.domain.value_objects.ingestion import IngestionTargets, MissingDeliveryCandidate


class IngestionTargetRepository(ABC):
    @abstractmethod
    def find_targets(self, dsp_id: int, window: DeliveryDateRange) -> IngestionTargets:
        """The active lines of the DSP over the window, split into those with a validated mapping and those without."""

    @abstractmethod
    def find_watched_campaign_ids(self, today: date) -> tuple[int, ...]:
        """The campaigns whose missing D-1 delivery is worth a flag: status active, with D-1 inside their dates."""

    @abstractmethod
    def find_lines_missing_delivery(self, dsp_id: int, window: DeliveryDateRange) -> tuple[MissingDeliveryCandidate, ...]:
        """Mapped lines of the DSP with no impressions in a period whose last day is inside the window.

        Only lines with a mapping validated on or before the period's last day are considered, so a period older
        than the mapping is never reported. The campaign's status is not part of the rule.
        """
