from abc import ABC, abstractmethod
from collections.abc import Iterator

from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey


class DspDeliveryClient(ABC):
    """What the ingestion service needs from a DSP. Adform defines the contract; Equativ and Displayce implement it."""

    @abstractmethod
    def fetch_delivery(self, date_range: DeliveryDateRange) -> Iterator[DspDeliveryRow]:
        """Stream the delivery the DSP reports for the range, bounds included.

        Streamed rather than listed: a full report is never held in memory as objects.
        """

    @abstractmethod
    def resolve_identifiers(self, external_campaign_id: str, external_line_item_id: str) -> ExternalLineKey | None:
        """Return the DSP's canonical key for an identifier pair, or None when the DSP does not know it."""
