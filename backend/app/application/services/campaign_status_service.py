from collections.abc import Callable
from datetime import date, timedelta

from app.domain.entities.campaign_status import CampaignStatusRow, FlightDeliveryFigures
from app.domain.repositories.campaign_status_repository import CampaignStatusRepository
from app.domain.services.carryover import delivery_target
from app.domain.services.missing_data import has_missing_data
from app.domain.services.pacing import calculate_pacing, pacing_flag


class CampaignStatusService:
    def __init__(self, repository: CampaignStatusRepository, today: Callable[[], date]) -> None:
        self._repository = repository
        self._today = today

    def list_status(self) -> list[CampaignStatusRow]:
        """One row per running flight of an active campaign, rows with any flag first, then agency, campaign, line."""
        today = self._today()
        day_before = today - timedelta(days=1)
        rows = [
            self._to_row(figures, day_before, has_missing_data(figures.campaign_latest_delivery_date, today))
            for figures in self._repository.list_running_flights(day_before)
        ]
        return sorted(rows, key=lambda r: (
            not (r.pacing_flag or r.missing_data_flag), r.agency_name, r.campaign_name, r.line_number,
        ))

    @staticmethod
    def _to_row(figures: FlightDeliveryFigures, day_before: date, missing_data_flag: bool) -> CampaignStatusRow:
        # The pacing and the ratio are measured against what the flight has to deliver: its contracted volume plus the
        # volume carried to it, whether or not that volume is billable.
        target = delivery_target(figures.contracted_impressions, figures.carryover)
        pacing = calculate_pacing(target, figures.flight_start, figures.flight_end, day_before, figures.delivered)
        ratio = float(figures.delivered) / target if target else None
        return CampaignStatusRow(
            campaign_id=figures.campaign_id, campaign_name=figures.campaign_name, agency_id=figures.agency_id,
            agency_name=figures.agency_name, line_number=figures.line_number,
            campaign_period_id=figures.campaign_period_id, period_year=figures.period_year,
            period_month=figures.period_month, flight_start=figures.flight_start, flight_end=figures.flight_end,
            contracted_impressions=figures.contracted_impressions, delivery_metric=figures.delivery_metric,
            delivered=figures.delivered, delivered_impressions=figures.delivered_impressions,
            delivery_ratio=ratio, pacing=pacing, pacing_flag=pacing_flag(pacing, figures.volume_commitment),
            missing_data_flag=missing_data_flag, volume_commitment=figures.volume_commitment,
            carryover=figures.carryover, delivery_target=target, flight_id=figures.flight_id,
        )
