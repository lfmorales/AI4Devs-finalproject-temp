from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CatalogLineSummary:
    """A DSP line item as the ingestion has seen it, and the campaign line it is mapped to, if any. No cost."""

    dsp_id: int
    external_campaign_id: str
    external_line_item_id: str
    campaign_name: str
    line_item_name: str
    line_start_date: date | None
    line_end_date: date | None
    first_seen_date: date
    last_seen_date: date
    last_impressions_date: date | None
    mapped_line_id: int | None


@dataclass(frozen=True)
class CatalogQuery:
    dsp_id: int | None = None
    text: str | None = None
    mapped: bool | None = None
    # Keeps the pairs whose last_seen_date is on or after this day: the last date with a row in the DSP.
    active_since: date | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class CatalogPage:
    items: list[CatalogLineSummary]
    total: int
