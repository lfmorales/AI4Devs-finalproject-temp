from datetime import date

from pydantic import BaseModel


class UnmappedLineResponse(BaseModel):
    """No cost and no price: this list is for finding the line to map, not for reading its economics."""

    id: int
    campaign_name: str
    line_number: int
    start_date: date
    end_date: date
    dsp_id: int
    dsp_name: str


class UnlinkLineResponse(BaseModel):
    campaign_line_id: int
    # Days of ingested delivery removed with the mapping.
    removed_delivery_days: int
