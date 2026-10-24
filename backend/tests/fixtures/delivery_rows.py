"""Builders for domain delivery objects. Literal dictionaries are not used as test data."""

from datetime import date
from decimal import Decimal

from app.domain.value_objects.delivery import DailyDelivery, DspDeliveryRow, ExternalLineKey


def external_key(campaign: str = "campaign-1", line_item: str = "line-item-1") -> ExternalLineKey:
    return ExternalLineKey(external_campaign_id=campaign, external_line_item_id=line_item)


def dsp_row(
    delivery_date: date,
    key: ExternalLineKey | None = None,
    impressions: int = 1000,
    clicks: int = 10,
    media_cost: Decimal = Decimal("5.0000"),
    measurable_impressions: int = 900,
    viewable_impressions: int = 700,
    banner_size: str | None = None,
    screen: str | None = None,
    line_format: str | None = None,
    unattributed: bool = False,
) -> DspDeliveryRow:
    return DspDeliveryRow(
        key=None if unattributed else key or external_key(),
        delivery_date=delivery_date,
        impressions=impressions,
        clicks=clicks,
        media_cost=media_cost,
        measurable_impressions=measurable_impressions,
        viewable_impressions=viewable_impressions,
        banner_size=banner_size,
        screen=screen,
        line_format=line_format,
    )


def daily_delivery(
    campaign_line_id: int,
    delivery_date: date,
    ingestion_batch_id: int = 1,
    impressions: int = 1000,
    media_cost: Decimal = Decimal("5.0000"),
    line_format: str | None = None,
) -> DailyDelivery:
    return DailyDelivery(
        campaign_line_id=campaign_line_id,
        ingestion_batch_id=ingestion_batch_id,
        delivery_date=delivery_date,
        impressions=impressions,
        clicks=10,
        media_cost=media_cost,
        measurable_impressions=900,
        viewable_impressions=700,
        banner_size=None,
        screen=None,
        line_format=line_format,
    )
