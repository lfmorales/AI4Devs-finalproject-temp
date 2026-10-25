from collections.abc import Iterable
from datetime import date

from app.domain.value_objects.delivery import DailyDelivery, DspDeliveryRow


def combine_daily_deliveries(
    attributed_rows: Iterable[tuple[int, DspDeliveryRow]],
    ingestion_batch_id: int,
) -> list[DailyDelivery]:
    """Sum the rows of every external line item mapped to a campaign line into one record per line and day.

    The grain allows a single record per line and day, so two line items on one line must be combined.
    Memory is bounded by the number of distinct line-and-day pairs, not by the number of rows read.
    """
    combined: dict[tuple[int, date], DailyDelivery] = {}
    for campaign_line_id, row in attributed_rows:
        key = (campaign_line_id, row.delivery_date)
        previous = combined.get(key)
        combined[key] = _from_row(campaign_line_id, ingestion_batch_id, row) if previous is None else _add(previous, row)
    return [combined[key] for key in sorted(combined)]


def _from_row(campaign_line_id: int, ingestion_batch_id: int, row: DspDeliveryRow) -> DailyDelivery:
    return DailyDelivery(
        campaign_line_id=campaign_line_id,
        ingestion_batch_id=ingestion_batch_id,
        delivery_date=row.delivery_date,
        impressions=row.impressions,
        clicks=row.clicks,
        media_cost=row.media_cost,
        measurable_impressions=row.measurable_impressions,
        viewable_impressions=row.viewable_impressions,
        banner_size=row.banner_size,
        screen=row.screen,
        line_format=row.line_format,
    )


def _add(total: DailyDelivery, row: DspDeliveryRow) -> DailyDelivery:
    return DailyDelivery(
        campaign_line_id=total.campaign_line_id,
        ingestion_batch_id=total.ingestion_batch_id,
        delivery_date=total.delivery_date,
        impressions=total.impressions + row.impressions,
        clicks=total.clicks + row.clicks,
        media_cost=total.media_cost + row.media_cost,
        measurable_impressions=total.measurable_impressions + row.measurable_impressions,
        viewable_impressions=total.viewable_impressions + row.viewable_impressions,
        # A descriptive attribute that the combined rows disagree on describes none of them.
        banner_size=_shared(total.banner_size, row.banner_size),
        screen=_shared(total.screen, row.screen),
        line_format=_shared(total.line_format, row.line_format),
    )


def _shared(current: str | None, incoming: str | None) -> str | None:
    return current if current == incoming else None
