from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class DeliveryDateRange:
    """An inclusive range of delivery dates, the unit an ingestion run replaces."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(f"start {self.start} must not be after end {self.end}")

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def days(self) -> list[date]:
        return [self.start + timedelta(days=offset) for offset in range((self.end - self.start).days + 1)]


@dataclass(frozen=True)
class ExternalLineKey:
    """How a DSP identifies a line item; the join key to a campaign line's DSP mapping."""

    external_campaign_id: str
    external_line_item_id: str


def _require_decimal_media_cost(media_cost: object) -> None:
    # Float cost drifts when summed over millions of rows.
    if not isinstance(media_cost, Decimal):
        raise TypeError(f"media_cost must be Decimal, not {type(media_cost)}")


@dataclass(frozen=True)
class DspDeliveryRow:
    """One day of delivery as a DSP reports it, before it is matched to a campaign line."""

    key: ExternalLineKey
    delivery_date: date
    impressions: int
    clicks: int
    media_cost: Decimal
    measurable_impressions: int
    viewable_impressions: int
    banner_size: str | None
    screen: str | None
    line_format: str | None

    def __post_init__(self) -> None:
        _require_decimal_media_cost(self.media_cost)


@dataclass(frozen=True)
class DailyDelivery:
    """Delivered volume for one campaign line and one day, as stored."""

    campaign_line_id: int
    ingestion_batch_id: int
    delivery_date: date
    impressions: int
    clicks: int
    media_cost: Decimal
    measurable_impressions: int
    viewable_impressions: int
    banner_size: str | None
    screen: str | None
    # Contrast data only; the configured channel is authoritative.
    line_format: str | None

    def __post_init__(self) -> None:
        _require_decimal_media_cost(self.media_cost)
