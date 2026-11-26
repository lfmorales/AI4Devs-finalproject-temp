from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.domain.value_objects.billing import AdjustmentEntry, BillingAdjustment
from app.domain.value_objects.flight import FlightWindow
from app.domain.value_objects.priced_flight import FlightFacts
from app.domain.value_objects.volume_commitment import VolumeCommitment


@dataclass(frozen=True)
class AdjustableFlight:
    """A flight as an adjustment needs it: where it sits, its commitment and whether a closing froze it."""

    flight_id: int
    window: FlightWindow
    volume_commitment: VolumeCommitment
    frozen: bool


class BillingAdjustmentTransaction(ABC):
    """The transactional boundary of adjusting a flight's billing: it lands whole or not at all."""

    @abstractmethod
    def get_flight(self, flight_id: int) -> AdjustableFlight | None: ...

    @abstractmethod
    def lock_month(self, year: int, month: int) -> None:
        """Serialise this write with the closing of the month and with the other edits of it, until the end."""

    @abstractmethod
    def flight_facts(self, flight_id: int) -> FlightFacts:
        """The facts the flight is priced with: the very ones the closing and the margin read use."""

    @abstractmethod
    def add_adjustment(
        self, flight_id: int, adjustment: BillingAdjustment, reason: str, user_id: int, at: datetime
    ) -> AdjustmentEntry: ...

    @abstractmethod
    def adjustments(self, flight_id: int) -> list[AdjustmentEntry]:
        """Every adjustment of the flight, latest first."""

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...
