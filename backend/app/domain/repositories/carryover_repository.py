from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.domain.services.carryover import PreviousFlight
from app.domain.value_objects.flight import FlightWindow
from app.domain.value_objects.volume_commitment import VolumeCommitment


@dataclass(frozen=True)
class CarryoverFlight:
    """A flight as a carry-over needs it. Volumes are in the unit of `delivery_metric`; `month_closed` is whether its
    month holds a closing header."""

    flight_id: int
    line_id: int
    window: FlightWindow
    contracted: int
    carryover: int
    carryover_billable: bool
    delivery_metric: str
    volume_commitment: VolumeCommitment
    month_closed: bool


@dataclass(frozen=True)
class LineFlight:
    flight_id: int
    window: FlightWindow


class CarryoverTransaction(ABC):
    """The transactional boundary of writing a carry-over or its billable flag: it lands whole or not at all."""

    @abstractmethod
    def get_flight(self, flight_id: int) -> CarryoverFlight | None: ...

    @abstractmethod
    def lock_month(self, year: int, month: int) -> None:
        """Serialise this write with the closing of the month and with the other edits of it, until the end."""

    @abstractmethod
    def line_flights(self, line_id: int) -> list[LineFlight]:
        """Every flight of the line with its window."""

    @abstractmethod
    def previous_flight_figures(self, flight_id: int) -> PreviousFlight:
        """What the flight had to deliver (contracted plus its carry-over) and what its line delivered inside its window,
        as stored now, in the unit of its metric."""

    @abstractmethod
    def write_carryover(self, flight_id: int, volume: int, reason: str, user_id: int, at: datetime) -> None: ...

    @abstractmethod
    def write_billable(self, flight_id: int, billable: bool, user_id: int, at: datetime) -> None: ...

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...
