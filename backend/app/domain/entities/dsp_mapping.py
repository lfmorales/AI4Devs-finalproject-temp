from dataclasses import dataclass
from datetime import date, datetime

from app.domain.value_objects.delivery import ExternalLineKey


@dataclass(frozen=True)
class DspMapping:
    """Binds a campaign line to a DSP's identifiers. validated_at is set only when the DSP knew the pair."""

    id: int
    campaign_line_id: int
    dsp_id: int
    key: ExternalLineKey
    validated_at: datetime | None


@dataclass(frozen=True)
class LineDsp:
    """The DSP a campaign line runs on."""

    dsp_id: int
    dsp_name: str
    # The first day of the line's own dates; None where the caller did not need it.
    line_start_date: date | None = None
