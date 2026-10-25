from abc import ABC, abstractmethod
from collections.abc import Iterable

from app.domain.value_objects.delivery import DeliveryDateRange, ExternalLineKey, RetainedDelivery


class IngestionExceptionRepository(ABC):
    @abstractmethod
    def delete_retained_range(self, dsp_id: int, window: DeliveryDateRange) -> None:
        """Delete the retained delivery of every unmatched-delivery exception of the DSP dated inside the window."""

    @abstractmethod
    def get_or_create_unmatched(self, dsp_id: int, key: ExternalLineKey, batch_id: int) -> int:
        """The id of the exception for this DSP and pair, whatever its status, created open if there is none.

        An existing exception is returned untouched: a resolved one is never reopened here.
        """

    @abstractmethod
    def add_retained(self, exception_id: int, rows: Iterable[RetainedDelivery]) -> None:
        """Store retained delivery rows, one per date, for an exception."""

    @abstractmethod
    def refresh_unmatched_date_spans(self, dsp_id: int) -> None:
        """Set first_date and last_date of the DSP's unmatched exceptions from their retained delivery.

        An exception with no retained delivery left keeps the dates it had.
        """

    @abstractmethod
    def record_missing_delivery(self, campaign_line_id: int, campaign_period_id: int, batch_id: int) -> bool:
        """Record a missing-delivery exception for the line and period; True if it was new, False if it existed."""
