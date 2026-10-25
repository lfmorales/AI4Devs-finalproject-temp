from collections import Counter
from collections.abc import Sequence

from app.domain.exceptions import (
    FlightVolumeNotPositiveError,
    FlightVolumesIncompleteError,
    FlightVolumesMismatchError,
)
from app.domain.value_objects.flight import FlightWindow, MonthlyVolume


def validate_explicit_volumes(
    total: int, flights: Sequence[FlightWindow], monthly_volumes: Sequence[MonthlyVolume]
) -> tuple[int, ...]:
    """Check the volumes a purchase order states per month against a line's flights.

    They must name exactly the months of the flights, once each (coverage), every one must be positive,
    and they must add up to the line's total. The checks run in that order. The volumes come back in the
    order of the flights.
    """
    stated = Counter((volume.period_year, volume.period_month) for volume in monthly_volumes)
    expected = {(flight.period_year, flight.period_month) for flight in flights}
    if set(stated) != expected or any(count > 1 for count in stated.values()):
        raise FlightVolumesIncompleteError("monthly volumes must cover exactly the months the line runs in")

    if any(volume.volume <= 0 for volume in monthly_volumes):
        raise FlightVolumeNotPositiveError("every monthly volume must be positive")

    if sum(volume.volume for volume in monthly_volumes) != total:
        raise FlightVolumesMismatchError("monthly volumes must add up to the line's total")

    by_month = {(volume.period_year, volume.period_month): volume.volume for volume in monthly_volumes}
    return tuple(by_month[(flight.period_year, flight.period_month)] for flight in flights)
