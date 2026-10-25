from app.domain.exceptions import AmbiguousMappingError, LineNotFoundError, MappingNotFoundError
from app.domain.repositories.line_mapping_removal_repository import LineMappingRemovalRepository


class LineMappingRemovalService:
    """Removes the only mapping of a line together with the delivery ingested through it, or nothing.

    The delivery of a line can only come from its mapping while the API is the only ingestion route; with several
    mappings it cannot be told which delivery came from which, so nothing is removed. Reopening the exception is
    out of scope: the delivery reappears as unmatched at the next ingestion.
    """

    def __init__(self, repository: LineMappingRemovalRepository) -> None:
        self._repository = repository

    def unlink(self, campaign_line_id: int) -> int:
        """Return how many days of delivery were removed."""
        try:
            removed_days = self._unlink(campaign_line_id)
        except BaseException:
            self._repository.rollback()
            raise
        self._repository.commit()
        return removed_days

    def _unlink(self, campaign_line_id: int) -> int:
        if not self._repository.line_exists(campaign_line_id):
            raise LineNotFoundError(f"campaign line {campaign_line_id} does not exist")
        mapping_ids = self._repository.mapping_ids(campaign_line_id)
        if not mapping_ids:
            raise MappingNotFoundError(f"campaign line {campaign_line_id} has no mapping")
        if len(mapping_ids) > 1:
            raise AmbiguousMappingError(f"campaign line {campaign_line_id} has several mappings")
        self._repository.delete_mapping(mapping_ids[0])
        return self._repository.delete_deliveries(campaign_line_id)
