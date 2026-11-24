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

    @classmethod
    def from_raw(cls, external_campaign_id: int | str, external_line_item_id: int | str) -> "ExternalLineKey":
        """Build a key from what a DSP reports (often integers) or a mapping stores (text), as text on both sides."""
        return cls(str(external_campaign_id).strip(), str(external_line_item_id).strip())


@dataclass(frozen=True)
class LineCatalogInfo:
    """What a DSP says about a line item next to its delivery: the names and the line's own dates."""

    campaign_name: str
    line_item_name: str
    line_start_date: date | None
    line_end_date: date | None


def _require_decimal_media_cost(media_cost: object) -> None:
    # Float cost drifts when summed over millions of rows.
    _require_decimal("media_cost", media_cost)


def _require_decimal(name: str, amount: object) -> None:
    if not isinstance(amount, Decimal):
        raise TypeError(f"{name} must be Decimal, not {type(amount)}")


# What a DSP such as Equativ bills next to the delivery; Adform reports none of them, so its rows carry zeros.
_REPORTED_AMOUNTS = ("buyer_spend", "reported_revenue", "third_party_data_cost", "audience_data_cost")


def _require_decimal_amounts(holder: object) -> None:
    for name in _REPORTED_AMOUNTS:
        _require_decimal(name, getattr(holder, name))


@dataclass(frozen=True)
class DspDeliveryRow:
    """One day of delivery as a DSP reports it, before it is matched to a campaign line."""

    # None when the DSP reports delivery without an attributed line item.
    key: ExternalLineKey | None
    delivery_date: date
    impressions: int
    clicks: int
    media_cost: Decimal
    measurable_impressions: int
    viewable_impressions: int
    banner_size: str | None
    screen: str | None
    line_format: str | None
    # OTS (the delivery of DOOH lines, four places) and video completions: absolute counts, never a rate.
    ots: Decimal
    video_completions: int
    # The buyer's spend, GeoQ's revenue as the DSP reports it (Equativ's curator margin) and the package's data costs.
    # Never a media cost: the buyer's spend is not what GeoQ pays.
    buyer_spend: Decimal
    reported_revenue: Decimal
    third_party_data_cost: Decimal
    audience_data_cost: Decimal
    # Only for attributed rows from a DSP that names its line items.
    catalog: LineCatalogInfo | None = None

    def __post_init__(self) -> None:
        _require_decimal_media_cost(self.media_cost)
        _require_decimal_amounts(self)


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
    # Absolute counts, summed over the combined rows; a rate is never stored.
    ots: Decimal
    video_completions: int
    # Exact sums over the combined rows; zero for a DSP that reports none of them.
    buyer_spend: Decimal
    reported_revenue: Decimal
    third_party_data_cost: Decimal
    audience_data_cost: Decimal

    def __post_init__(self) -> None:
        _require_decimal_media_cost(self.media_cost)
        _require_decimal_amounts(self)


@dataclass(frozen=True)
class RetainedDelivery:
    """Delivery kept on an unmatched-delivery exception for one pair and date, instead of being dropped."""

    key: ExternalLineKey
    delivery_date: date
    impressions: int
    clicks: int
    media_cost: Decimal
    measurable_impressions: int
    viewable_impressions: int

    def __post_init__(self) -> None:
        _require_decimal_media_cost(self.media_cost)
