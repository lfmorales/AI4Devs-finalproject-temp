from collections.abc import Collection, Iterable, Iterator

from app.domain.exceptions import DeliveryForUnknownLineError, DeliveryOutsideRangeError
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.value_objects.delivery import DailyDelivery, DeliveryDateRange


class DeliveryRangeReplacer:
    """Makes an ingestion run idempotent: the range is replaced, never appended to.

    Delete-then-insert rather than upsert on purpose: a DSP restatement can remove a line item's
    rows, and an upsert would leave the removed ones behind.
    """

    def __init__(self, unit_of_work: UnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    def replace_range(
        self,
        campaign_line_ids: Collection[int],
        date_range: DeliveryDateRange,
        deliveries: Iterable[DailyDelivery],
    ) -> int:
        """Replace the lines' delivery inside the range and return how many rows were stored."""
        stored_count = 0

        def _counted(rows: Iterator[DailyDelivery]) -> Iterator[DailyDelivery]:
            nonlocal stored_count
            for row in rows:
                stored_count += 1
                yield row

        # Delete and insert share one transaction: a failure partway must not leave the range half replaced.
        with self._unit_of_work as unit_of_work:
            unit_of_work.deliveries.delete_range(campaign_line_ids, date_range)
            unit_of_work.deliveries.add_all(_counted(self._within_run(campaign_line_ids, date_range, deliveries)))
        return stored_count

    @staticmethod
    def _within_run(
        campaign_line_ids: Collection[int],
        date_range: DeliveryDateRange,
        deliveries: Iterable[DailyDelivery],
    ) -> Iterator[DailyDelivery]:
        # A row outside the run would not have been deleted above, so storing it could duplicate a day.
        for delivery in deliveries:
            if delivery.campaign_line_id not in campaign_line_ids:
                raise DeliveryForUnknownLineError(f"line {delivery.campaign_line_id} is not part of this run")
            if not date_range.contains(delivery.delivery_date):
                raise DeliveryOutsideRangeError(f"{delivery.delivery_date} is outside {date_range}")
            yield delivery
