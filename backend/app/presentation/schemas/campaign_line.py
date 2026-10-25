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
