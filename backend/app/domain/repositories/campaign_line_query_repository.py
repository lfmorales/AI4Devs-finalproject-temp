from abc import ABC, abstractmethod

from app.domain.entities.unmapped_line import UnmappedLine


class CampaignLineQueryRepository(ABC):
    @abstractmethod
    def list_unmapped(self) -> list[UnmappedLine]:
        """The lines with no mapping at all (validated or not), ordered by campaign name and line number."""
