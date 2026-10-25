from abc import ABC, abstractmethod
from collections.abc import Iterable

from app.domain.value_objects.catalog import CatalogLineObservation


class DspCatalogRepository(ABC):
    @abstractmethod
    def upsert_all(self, dsp_id: int, observations: Iterable[CatalogLineObservation]) -> None:
        """Create the catalogue lines that do not exist and apply each observation over the ones that do
        (see CatalogLineObservation.merged_into)."""
