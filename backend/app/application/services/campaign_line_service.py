from app.domain.entities.unmapped_line import UnmappedLine
from app.domain.repositories.campaign_line_query_repository import CampaignLineQueryRepository


class CampaignLineService:
    def __init__(self, repository: CampaignLineQueryRepository) -> None:
        self._repository = repository

    def list_unmapped(self) -> list[UnmappedLine]:
        return self._repository.list_unmapped()
