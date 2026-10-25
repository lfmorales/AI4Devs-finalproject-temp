from datetime import date

import pytest

from app.domain.exceptions import (
    DomainError,
    FlightVolumeNotPositiveError,
    FlightVolumesIncompleteError,
    FlightVolumesMismatchError,
)
from app.domain.services.explicit_volumes import validate_explicit_volumes
from app.domain.value_objects.flight import FlightWindow, MonthlyVolume

FLIGHTS = [
    FlightWindow(2026, 8, date(2026, 8, 15), date(2026, 8, 31)),
    FlightWindow(2026, 9, date(2026, 9, 1), date(2026, 9, 30)),
    FlightWindow(2026, 10, date(2026, 10, 1), date(2026, 10, 10)),
]


def test_months_that_match_and_add_up_are_returned_in_flight_order():
    volumes = [MonthlyVolume(2026, 10, 200), MonthlyVolume(2026, 8, 300), MonthlyVolume(2026, 9, 500)]

    assert validate_explicit_volumes(1000, FLIGHTS, volumes) == (300, 500, 200)


def test_a_single_flight_takes_its_explicit_volume():
    assert validate_explicit_volumes(70, FLIGHTS[:1], [MonthlyVolume(2026, 8, 70)]) == (70,)


def test_a_missing_month_is_incomplete():
    volumes = [MonthlyVolume(2026, 8, 400), MonthlyVolume(2026, 9, 600)]

    with pytest.raises(FlightVolumesIncompleteError):
        validate_explicit_volumes(1000, FLIGHTS, volumes)


def test_a_repeated_month_is_incomplete():
    volumes = [
        MonthlyVolume(2026, 8, 300), MonthlyVolume(2026, 9, 300),
        MonthlyVolume(2026, 9, 200), MonthlyVolume(2026, 10, 200),
    ]

    with pytest.raises(FlightVolumesIncompleteError):
        validate_explicit_volumes(1000, FLIGHTS, volumes)


def test_a_month_the_line_does_not_reach_is_incomplete():
    volumes = [
        MonthlyVolume(2026, 8, 300), MonthlyVolume(2026, 9, 300),
        MonthlyVolume(2026, 10, 200), MonthlyVolume(2026, 11, 200),
    ]

    with pytest.raises(FlightVolumesIncompleteError):
        validate_explicit_volumes(1000, FLIGHTS, volumes)


def test_a_month_of_another_year_is_not_the_same_month():
    volumes = [MonthlyVolume(2026, 8, 300), MonthlyVolume(2026, 9, 500), MonthlyVolume(2027, 10, 200)]

    with pytest.raises(FlightVolumesIncompleteError):
        validate_explicit_volumes(1000, FLIGHTS, volumes)


def test_no_volumes_at_all_is_incomplete():
    with pytest.raises(FlightVolumesIncompleteError):
        validate_explicit_volumes(1000, FLIGHTS, [])


@pytest.mark.parametrize("sum_difference", [-1, 1])
def test_a_sum_that_differs_by_one_is_a_mismatch(sum_difference: int):
    volumes = [MonthlyVolume(2026, 8, 300), MonthlyVolume(2026, 9, 500), MonthlyVolume(2026, 10, 200 + sum_difference)]

    with pytest.raises(FlightVolumesMismatchError):
        validate_explicit_volumes(1000, FLIGHTS, volumes)


@pytest.mark.parametrize("bad_volume", [0, -50])
def test_a_volume_that_is_not_positive_is_refused(bad_volume: int):
    volumes = [MonthlyVolume(2026, 8, bad_volume), MonthlyVolume(2026, 9, 1000 - bad_volume - 200), MonthlyVolume(2026, 10, 200)]

    with pytest.raises(FlightVolumeNotPositiveError):
        validate_explicit_volumes(1000, FLIGHTS, volumes)


def test_coverage_is_checked_before_positivity_and_positivity_before_the_sum():
    with pytest.raises(FlightVolumesIncompleteError):
        validate_explicit_volumes(1000, FLIGHTS, [MonthlyVolume(2026, 8, 0), MonthlyVolume(2026, 9, 5)])
    with pytest.raises(FlightVolumeNotPositiveError):
        validate_explicit_volumes(
            1000, FLIGHTS, [MonthlyVolume(2026, 8, 0), MonthlyVolume(2026, 9, 5), MonthlyVolume(2026, 10, 5)]
        )


def test_the_three_errors_are_domain_errors():
    for error in (FlightVolumesIncompleteError, FlightVolumesMismatchError, FlightVolumeNotPositiveError):
        assert issubclass(error, DomainError)
