from abc import ABC, abstractmethod
from datetime import date

from app.domain.entities.campaign_status import FlightDeliveryFigures


class CampaignStatusRepository(ABC):
    """Reads the flight-level figures behind the daily status."""

    @abstractmethod
    def list_running_flights(self, as_of: date) -> list[FlightDeliveryFigures]:
        """The flights of `active` campaigns whose window contains `as_of`, with their delivery summed up to it.

        Delivery is aggregated by the store; no delivery row is returned.
        """
