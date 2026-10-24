from collections.abc import Collection, Iterable
from datetime import date

from app.domain.repositories.delivery_repository import DeliveryRepository
from app.domain.value_objects.delivery import DailyDelivery, DeliveryDateRange


class InMemoryDeliveryRepository(DeliveryRepository):
    """Deliveries keyed by line and day, the grain the real table enforces with a unique constraint."""

    def __init__(self, deliveries: Iterable[DailyDelivery] = ()) -> None:
        self.rows: dict[tuple[int, date], DailyDelivery] = {}
        self.add_all(deliveries)

    def delete_range(self, campaign_line_ids: Collection[int], date_range: DeliveryDateRange) -> None:
        self.rows = {
            (line_id, day): row
            for (line_id, day), row in self.rows.items()
            if not (line_id in campaign_line_ids and date_range.contains(day))
        }

    def add_all(self, deliveries: Iterable[DailyDelivery]) -> None:
        for delivery in deliveries:
            self.rows[(delivery.campaign_line_id, delivery.delivery_date)] = delivery

    def impressions_by_line_and_day(self) -> dict[tuple[int, date], int]:
        return {key: row.impressions for key, row in sorted(self.rows.items())}
