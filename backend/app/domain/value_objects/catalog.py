from dataclasses import dataclass, replace
from datetime import date

from app.domain.value_objects.delivery import ExternalLineKey


@dataclass(frozen=True)
class CatalogLineObservation:
    """What one run saw of a DSP line item: its names and dates and the delivery dates it was seen on."""

    key: ExternalLineKey
    campaign_name: str
    line_item_name: str
    line_start_date: date | None
    line_end_date: date | None
    first_seen_date: date
    last_seen_date: date
    # The latest date with impressions above zero; None when every row seen was zeros.
    last_impressions_date: date | None

    def merged_into(self, stored: "CatalogLineObservation") -> "CatalogLineObservation":
        """This observation applied over what the catalogue already holds.

        The seen dates only widen. Names and dates are replaced only when this observation reaches at least as
        far as the stored one, so loading an older range never overwrites a newer name with a stale one.
        """
        current = self if self.last_seen_date >= stored.last_seen_date else stored
        impressions_dates = [d for d in (stored.last_impressions_date, self.last_impressions_date) if d is not None]
        return replace(
            current,
            first_seen_date=min(stored.first_seen_date, self.first_seen_date),
            last_seen_date=max(stored.last_seen_date, self.last_seen_date),
            last_impressions_date=max(impressions_dates, default=None),
        )
