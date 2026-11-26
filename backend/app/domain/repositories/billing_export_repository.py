from abc import ABC, abstractmethod

from app.domain.value_objects.billing_export import ExportRow


class BillingExportRepository(ABC):
    """Reads what the closings of a month froze. Writes nothing."""

    @abstractmethod
    def month_is_closed(self, year: int, month: int) -> bool:
        """Whether the month holds at least one closing header."""

    @abstractmethod
    def frozen_rows(self, year: int, month: int) -> list[ExportRow]:
        """One row per flight frozen by any closing of the month, by agency, campaign, line number and flight start."""
