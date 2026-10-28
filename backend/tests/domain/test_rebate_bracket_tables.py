"""A bracket table starts at 0, is contiguous and ends open; anything else is a domain error with a code."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.exceptions import RebateRuleError
from app.domain.value_objects.rebate import Bracket, RebateSchedule


def _schedule(*brackets: Bracket) -> RebateSchedule:
    return RebateSchedule(
        schedule_id=1, group_id=1, agency_id=None, channel=None, scope=None,
        valid_from=date(2026, 1, 1), valid_to=None, brackets=brackets,
    )


def _rejected(*brackets: Bracket) -> str:
    with pytest.raises(RebateRuleError) as raised:
        _schedule(*brackets)
    return raised.value.code


def test_a_valid_table_is_accepted():
    schedule = _schedule(
        Bracket(Decimal(0), Decimal(100_000), Decimal("0.15")),
        Bracket(Decimal(100_000), Decimal(500_000), Decimal("0.20")),
        Bracket(Decimal(500_000), None, Decimal("0.25")),
    )

    assert len(schedule.brackets) == 3


def test_a_table_that_does_not_start_at_zero_is_rejected():
    assert _rejected(Bracket(Decimal(1_000), None, Decimal("0.15"))) == "bracket_table_must_start_at_zero"


def test_a_table_with_a_gap_is_rejected():
    code = _rejected(
        Bracket(Decimal(0), Decimal(100_000), Decimal("0.15")),
        Bracket(Decimal(120_000), None, Decimal("0.20")),
    )

    assert code == "bracket_table_not_contiguous"


def test_a_table_with_an_overlap_is_rejected():
    code = _rejected(
        Bracket(Decimal(0), Decimal(100_000), Decimal("0.15")),
        Bracket(Decimal(90_000), None, Decimal("0.20")),
    )

    assert code == "bracket_table_not_contiguous"


def test_a_table_whose_last_bracket_is_bounded_is_rejected():
    code = _rejected(
        Bracket(Decimal(0), Decimal(100_000), Decimal("0.15")),
        Bracket(Decimal(100_000), Decimal(500_000), Decimal("0.20")),
    )

    assert code == "last_bracket_must_be_open"


def test_an_open_bracket_in_the_middle_is_rejected():
    code = _rejected(
        Bracket(Decimal(0), None, Decimal("0.15")),
        Bracket(Decimal(100_000), None, Decimal("0.20")),
    )

    assert code == "bracket_table_not_contiguous"


def test_an_empty_table_is_rejected_with_its_own_code():
    assert _rejected() == "bracket_table_empty"


def test_a_bracket_with_an_upper_not_above_its_lower_is_rejected():
    assert _rejected(Bracket(Decimal(0), Decimal(0), Decimal("0.15"))) == "bracket_table_not_contiguous"
