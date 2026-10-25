from abc import ABC, abstractmethod

from app.domain.entities.dsp_catalog import CatalogPage, CatalogQuery


class DspCatalogQueryRepository(ABC):
    @abstractmethod
    def search(self, query: CatalogQuery) -> CatalogPage:
        """One page of the catalogue, newest last_seen_date first, and the total that matches the filters."""
