from collections.abc import Iterable

from app.domain.repositories.ingestion_exception_repository import IngestionExceptionRepository
from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey, RetainedDelivery


def retain(previous: RetainedDelivery | None, key: ExternalLineKey, row: DspDeliveryRow) -> RetainedDelivery:
    """Add an unmatched row to what is already retained for its pair and date."""
    if previous is None:
        return RetainedDelivery(
            key, row.delivery_date, row.impressions, row.clicks, row.media_cost,
            row.measurable_impressions, row.viewable_impressions,
        )
    return RetainedDelivery(
        key, row.delivery_date,
        previous.impressions + row.impressions, previous.clicks + row.clicks,
        previous.media_cost + row.media_cost,
        previous.measurable_impressions + row.measurable_impressions,
        previous.viewable_impressions + row.viewable_impressions,
    )


def has_something_to_work(row: DspDeliveryRow) -> bool:
    """An unmatched row is worth an exception only if it carries impressions or cost."""
    return row.impressions != 0 or row.media_cost != 0


class UnmatchedDeliveryRecorder:
    """Keeps unmatched delivery as one exception per DSP and pair, replacing the retained dates of the window."""

    def record(
        self,
        exceptions: IngestionExceptionRepository,
        dsp_id: int,
        batch_id: int,
        window: DeliveryDateRange,
        retained: Iterable[RetainedDelivery],
    ) -> None:
        # Replace, not add: running the window again must not duplicate a day, and a restatement may drop one.
        exceptions.delete_retained_range(dsp_id, window)
        by_pair: dict[ExternalLineKey, list[RetainedDelivery]] = {}
        for row in retained:
            by_pair.setdefault(row.key, []).append(row)
        for key in sorted(by_pair, key=lambda pair: (pair.external_campaign_id, pair.external_line_item_id)):
            exception_id = exceptions.get_or_create_unmatched(dsp_id, key, batch_id)
            exceptions.add_retained(exception_id, by_pair[key])
        exceptions.refresh_unmatched_date_spans(dsp_id)
