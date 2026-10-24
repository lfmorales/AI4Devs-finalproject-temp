from collections.abc import Iterable, Iterator

from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey


class InMemoryDspDeliveryClient(DspDeliveryClient):
    """A DSP that serves a fixed list of rows. Keys seen in the rows are resolvable."""

    def __init__(self, rows: Iterable[DspDeliveryRow], known_keys: Iterable[ExternalLineKey] = ()) -> None:
        self._rows = list(rows)
        self._known_keys = {row.key for row in self._rows} | set(known_keys)
        self.requested_ranges: list[DeliveryDateRange] = []

    def fetch_delivery(self, date_range: DeliveryDateRange) -> Iterator[DspDeliveryRow]:
        self.requested_ranges.append(date_range)
        return (row for row in self._rows if date_range.contains(row.delivery_date))

    def resolve_identifiers(self, external_campaign_id: str, external_line_item_id: str) -> ExternalLineKey | None:
        candidate = ExternalLineKey(external_campaign_id, external_line_item_id)
        return candidate if candidate in self._known_keys else None
