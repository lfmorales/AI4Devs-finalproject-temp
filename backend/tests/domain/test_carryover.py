"""The carry-over of a flight (campaign/carryover): the previous flight, its shortfall and the rules a carry-over obeys.

Worked example: an October flight of 500,000 impressions delivered 400,000, so 100,000 fell short and may be carried
to the November flight of the same line, whose delivery target becomes 600,000.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.domain.exceptions import CarryoverError
from app.domain.services.carryover import (
    PreviousFlight,
    delivery_target,
    previous_flight_of,
    shortfall,
    validate_carryover,
)
from app.domain.value_objects.flight import FlightWindow

OCTOBER = FlightWindow(2026, 10, date(2026, 10, 1), date(2026, 10, 31))
NOVEMBER = FlightWindow(2026, 11, date(2026, 11, 1), date(2026, 11, 30))
DECEMBER = FlightWindow(2026, 12, date(2026, 12, 1), date(2026, 12, 31))
JANUARY = FlightWindow(2027, 1, date(2027, 1, 1), date(2027, 1, 31))
D_MINUS_1 = date(2026, 11, 5)  # October has ended, November is running
REASON = "Recuperar lo no entregado en octubre"


def _previous(
    contracted: int = 500_000, carryover: int = 0, delivered: str = "400000", end: date = OCTOBER.flight_end
) -> PreviousFlight:
    return PreviousFlight(flight_end=end, delivery_target=contracted + carryover, delivered=Decimal(delivered))


_DEFAULT_PREVIOUS = _previous()


def _validate(
    volume: int,
    previous: PreviousFlight | None = _DEFAULT_PREVIOUS,
    month_closed: bool = False,
    reason: str = REASON,
    as_of: date = D_MINUS_1,
) -> None:
    validate_carryover(
        volume=volume, reason=reason, previous=previous, receiving_month_closed=month_closed, as_of=as_of
    )


def _code(volume: int, **kwargs: Any) -> str:
    with pytest.raises(CarryoverError) as raised:
        _validate(volume, **kwargs)
    return raised.value.code


# ---------------------------------------------------------------- the delivery target


def test_the_delivery_target_is_the_contracted_volume_plus_the_carry_over() -> None:
    assert delivery_target(500_000, 100_000) == 600_000
    assert delivery_target(500_000, 0) == 500_000


# ---------------------------------------------------------------- the previous flight


def test_the_previous_flight_is_the_latest_one_of_the_line_that_ends_before_the_receiving_flight_starts() -> None:
    windows = [DECEMBER, OCTOBER, NOVEMBER]

    assert previous_flight_of(windows, DECEMBER) == NOVEMBER
    assert previous_flight_of(windows, NOVEMBER) == OCTOBER


def test_the_first_flight_of_a_line_has_no_previous_flight() -> None:
    assert previous_flight_of([OCTOBER, NOVEMBER], OCTOBER) is None
    assert previous_flight_of([], OCTOBER) is None


def test_a_flight_is_never_its_own_previous_flight() -> None:
    assert previous_flight_of([NOVEMBER], NOVEMBER) is None


def test_the_previous_flight_of_january_is_december_of_the_year_before() -> None:
    assert previous_flight_of([DECEMBER, JANUARY], JANUARY) == DECEMBER


# ---------------------------------------------------------------- the shortfall


def test_the_shortfall_is_the_target_of_the_previous_flight_less_what_was_delivered() -> None:
    assert shortfall(_previous()) == Decimal("100000")


def test_a_previous_flight_that_delivered_its_target_or_more_has_no_shortfall() -> None:
    assert shortfall(_previous(delivered="500000")) == Decimal(0)
    assert shortfall(_previous(delivered="520000")) == Decimal(0)


def test_the_shortfall_counts_the_carry_over_the_previous_flight_received() -> None:
    # 500,000 contracted + 50,000 carried in = 550,000 to deliver; 480,000 delivered.
    assert shortfall(_previous(carryover=50_000, delivered="480000")) == Decimal("70000")


def test_the_shortfall_of_a_dooh_flight_keeps_the_decimals_of_its_ots() -> None:
    assert shortfall(_previous(delivered="299999.5000", contracted=300_000)) == Decimal("0.5000")


# ---------------------------------------------------------------- the rules


def test_a_carry_over_up_to_the_shortfall_is_accepted() -> None:
    _validate(100_000)
    _validate(1)


def test_a_carry_over_above_the_shortfall_is_refused_naming_the_shortfall() -> None:
    with pytest.raises(CarryoverError) as raised:
        _validate(100_001)

    assert raised.value.code == "carryover_exceeds_shortfall"
    assert "100000" in str(raised.value)


def test_a_previous_flight_that_delivered_its_target_leaves_nothing_to_carry() -> None:
    assert _code(1, previous=_previous(delivered="520000")) == "carryover_exceeds_shortfall"


def test_the_carry_over_of_a_dooh_flight_cannot_exceed_its_fractional_shortfall() -> None:
    previous = _previous(contracted=300_000, delivered="299999.5000")

    assert _code(1, previous=previous) == "carryover_exceeds_shortfall"


def test_a_flight_with_no_previous_flight_receives_nothing() -> None:
    assert _code(1, previous=None) == "no_previous_flight"


def test_the_previous_flight_must_have_ended() -> None:
    running = _previous(end=date(2026, 11, 30))

    assert _code(1, previous=running, as_of=date(2026, 11, 29)) == "previous_flight_not_ended"


def test_a_previous_flight_ending_on_the_day_counted_has_ended() -> None:
    _validate(1, previous=_previous(end=D_MINUS_1), as_of=D_MINUS_1)


def test_a_closed_month_receives_no_carry_over() -> None:
    assert _code(1, month_closed=True) == "month_closed"


def test_december_may_carry_to_january() -> None:
    december = _previous(end=DECEMBER.flight_end, delivered="450000")

    _validate(50_000, previous=december, as_of=date(2027, 1, 5))


def test_a_volume_of_zero_removes_the_carry_over_and_still_needs_a_reason() -> None:
    _validate(0)
    assert _code(0, reason="") == "invalid_carryover"


def test_a_volume_of_zero_is_refused_in_a_closed_month() -> None:
    assert _code(0, month_closed=True) == "month_closed"


@pytest.mark.parametrize("reason", ["", "   ", "\n\t"], ids=["empty", "spaces", "whitespace"])
def test_the_reason_is_mandatory(reason: str) -> None:
    assert _code(1, reason=reason) == "invalid_carryover"


def test_a_negative_volume_is_refused() -> None:
    assert _code(-1) == "invalid_carryover"


def test_a_volume_that_is_not_a_whole_number_is_refused() -> None:
    with pytest.raises(CarryoverError) as raised:
        _validate(1.5)  # type: ignore[arg-type]

    assert raised.value.code == "invalid_carryover"


def test_a_boolean_is_not_a_volume() -> None:
    with pytest.raises(CarryoverError):
        _validate(True)


def test_the_checks_run_in_the_order_of_the_specification() -> None:
    # Everything is wrong at once: the first rule of the list is the one reported.
    unstarted = _previous(end=date(2026, 11, 30), delivered="500000")

    assert _code(1, previous=None, month_closed=True) == "no_previous_flight"
    assert _code(1, previous=unstarted, month_closed=True, as_of=date(2026, 11, 5)) == "previous_flight_not_ended"
    assert _code(1, previous=_previous(delivered="500000"), month_closed=True) == "carryover_exceeds_shortfall"
    assert _code(-1, previous=None, month_closed=True) == "invalid_carryover"
