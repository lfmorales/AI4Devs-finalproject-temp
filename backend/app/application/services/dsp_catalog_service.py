from app.domain.entities.dsp_catalog import CatalogPage, CatalogQuery
from app.domain.repositories.dsp_catalog_query_repository import DspCatalogQueryRepository


class DspCatalogService:
    def __init__(self, repository: DspCatalogQueryRepository) -> None:
        self._repository = repository

    def search(self, query: CatalogQuery) -> CatalogPage:
        return self._repository.search(query)
