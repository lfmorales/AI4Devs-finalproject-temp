from collections.abc import Sequence
from datetime import date

from app.domain.entities.campaign import CampaignPeriod
from app.domain.value_objects.flight import FlightWindow


def generate_flights(line_start: date, line_end: date, periods: Sequence[CampaignPeriod]) -> list[FlightWindow]:
    """One flight for each campaign period the line's dates intersect, clipped to the intersection.

    A period the line does not touch gets none. The flights come back in the order of the periods given.
    """
    if line_start > line_end:
        raise ValueError("line start must be <= line end")

    flights: list[FlightWindow] = []
    for period in periods:
        flight_start = max(line_start, period.period_start)
        flight_end = min(line_end, period.period_end)
        if flight_start <= flight_end:
            flights.append(FlightWindow(period.period_year, period.period_month, flight_start, flight_end))
    return flights
