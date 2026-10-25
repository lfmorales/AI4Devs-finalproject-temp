from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class UnmappedLine:
    """A campaign line with no DSP mapping: the ones operations still has to map. No cost and no price."""

    id: int
    campaign_name: str
    line_number: int
    start_date: date
    end_date: date
    dsp_id: int
    dsp_name: str
