from abc import ABC, abstractmethod
from datetime import date

from app.domain.entities.dsp_catalog import CatalogPage, CatalogQuery
from app.domain.value_objects.delivery import ExternalLineKey


class DspCatalogQueryRepository(ABC):
    @abstractmethod
    def search(self, query: CatalogQuery) -> CatalogPage:
        """One page of the catalogue, newest last_seen_date first, and the total that matches the filters."""

    @abstractmethod
    def find_last_impressions_date(self, dsp_id: int, key: ExternalLineKey) -> date | None:
        """The latest date the pair delivered impressions, or None when it is not in the catalogue or never did."""
