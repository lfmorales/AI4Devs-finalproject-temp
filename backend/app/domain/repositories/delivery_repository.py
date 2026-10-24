from abc import ABC, abstractmethod
from collections.abc import Collection, Iterable

from app.domain.value_objects.delivery import DailyDelivery, DeliveryDateRange


class DeliveryRepository(ABC):
    """Write side of daily deliveries. Aggregation for the status view belongs to a separate read interface."""

    @abstractmethod
    def delete_range(self, campaign_line_ids: Collection[int], date_range: DeliveryDateRange) -> None:
        """Delete every delivery of the given lines dated inside the range, bounds included."""

    @abstractmethod
    def add_all(self, deliveries: Iterable[DailyDelivery]) -> None:
        """Store the deliveries, consuming the iterable lazily so a large run is never held as a list."""
