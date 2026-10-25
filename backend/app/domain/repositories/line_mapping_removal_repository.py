from abc import ABC, abstractmethod


class LineMappingRemovalRepository(ABC):
    """The writes of removing a line's mapping, which share one transaction: nothing commits until `commit`."""

    @abstractmethod
    def line_exists(self, campaign_line_id: int) -> bool: ...

    @abstractmethod
    def mapping_ids(self, campaign_line_id: int) -> list[int]: ...

    @abstractmethod
    def delete_mapping(self, mapping_id: int) -> None: ...

    @abstractmethod
    def delete_deliveries(self, campaign_line_id: int) -> int:
        """Delete every ingested delivery of the line and return how many days that removes."""

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...
