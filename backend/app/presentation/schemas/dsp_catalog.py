from datetime import date

from pydantic import BaseModel


class DspCatalogItemResponse(BaseModel):
    """No cost: the catalogue says what exists in the DSP, not what it spent."""

    dsp_id: int
    external_campaign_id: str
    external_line_item_id: str
    campaign_name: str
    line_item_name: str
    line_start_date: date | None
    line_end_date: date | None
    first_seen_date: date
    # The last date with a row in the DSP, not real activity; last_impressions_date is the last with impressions.
    last_seen_date: date
    last_impressions_date: date | None
    mapped_line_id: int | None


class DspCatalogPageResponse(BaseModel):
    items: list[DspCatalogItemResponse]
    total: int
    limit: int
    offset: int
