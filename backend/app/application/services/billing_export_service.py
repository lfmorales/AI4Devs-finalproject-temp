from app.domain.exceptions import MonthNotClosedError
from app.domain.repositories.billing_export_repository import BillingExportRepository
from app.domain.services.billing_export import billing_csv, export_file_name


class BillingExportService:
    """Builds the CSV of a closed month from its snapshots only: a later delivery, adjustment or master never moves it.
    Writes nothing."""

    def __init__(self, repository: BillingExportRepository) -> None:
        self._repository = repository

    def export(self, year: int, month: int) -> tuple[str, bytes]:
        """The file name and the file."""
        if not self._repository.month_is_closed(year, month):
            raise MonthNotClosedError(year, month)
        return export_file_name(year, month), billing_csv(self._repository.frozen_rows(year, month))
