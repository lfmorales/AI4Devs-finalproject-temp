from datetime import date

from app.domain.value_objects.catalog import CatalogLineObservation
from app.domain.value_objects.delivery import DspDeliveryRow, ExternalLineKey


class CatalogObserver:
    """Folds the rows of a run into one observation per pair, without holding the rows.

    Only attributed rows that carry catalogue information count; rows of zeros count as seen. The names and dates
    are those of the pair's latest row.
    """

    def __init__(self) -> None:
        self._observations: dict[ExternalLineKey, CatalogLineObservation] = {}

    def add(self, row: DspDeliveryRow) -> None:
        if row.key is None or row.catalog is None:
            return
        key = ExternalLineKey.from_raw(row.key.external_campaign_id, row.key.external_line_item_id)
        impressions_date: date | None = row.delivery_date if row.impressions > 0 else None
        observation = CatalogLineObservation(
            key=key,
            campaign_name=row.catalog.campaign_name,
            line_item_name=row.catalog.line_item_name,
            line_start_date=row.catalog.line_start_date,
            line_end_date=row.catalog.line_end_date,
            first_seen_date=row.delivery_date,
            last_seen_date=row.delivery_date,
            last_impressions_date=impressions_date,
        )
        stored = self._observations.get(key)
        self._observations[key] = observation if stored is None else observation.merged_into(stored)

    def observations(self) -> list[CatalogLineObservation]:
        return list(self._observations.values())
