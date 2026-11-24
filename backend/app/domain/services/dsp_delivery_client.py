from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator

from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey


class DspDeliveryClient(ABC):
    """What the ingestion service needs from a DSP. Adform defines the contract; Equativ and Displayce implement it."""

    def on_source_known(self, listener: Callable[[str], None]) -> None:
        """Have the next run hand its source to `listener` as soon as the DSP names it.

        Only a DSP whose source exists once the run has begun (Equativ's report) calls it; the others never do,
        so by default the listener is not kept.
        """

    @abstractmethod
    def fetch_delivery(self, date_range: DeliveryDateRange) -> Iterator[DspDeliveryRow]:
        """Stream the delivery the DSP reports for the range, bounds included.

        Streamed rather than listed: a full report is never held in memory as objects.
        """

    @abstractmethod
    def resolve_identifiers(self, external_campaign_id: str, external_line_item_id: str) -> ExternalLineKey | None:
        """Return the DSP's canonical key for an identifier pair, or None when the DSP does not know it."""
