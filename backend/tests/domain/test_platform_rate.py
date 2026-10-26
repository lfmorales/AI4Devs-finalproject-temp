"""The platform rate resolves most specific first: line, then agency, then campaign type, then system.

The system value is data handed to the function, never a constant inside it.
"""

import ast
import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.services import platform_rate
from app.domain.services.platform_rate import resolve_platform_rate
from app.domain.value_objects.platform_rate import PlatformRateLevel

SYSTEM = Decimal("1.00")
LINE = Decimal("0.80")
AGENCY = Decimal("1.20")
CAMPAIGN_TYPE = Decimal("1.50")


def test_a_line_rate_beats_every_other_level():
    resolved = resolve_platform_rate(system=SYSTEM, line=LINE, agency=AGENCY, campaign_type=CAMPAIGN_TYPE)

    assert resolved.rate == LINE
    assert resolved.level is PlatformRateLevel.LINE


def test_an_agency_rate_beats_the_campaign_type_and_the_system():
    resolved = resolve_platform_rate(system=SYSTEM, agency=AGENCY, campaign_type=CAMPAIGN_TYPE)

    assert resolved.rate == AGENCY
    assert resolved.level is PlatformRateLevel.AGENCY


def test_a_campaign_type_rate_beats_the_system():
    resolved = resolve_platform_rate(system=SYSTEM, campaign_type=CAMPAIGN_TYPE)

    assert resolved.rate == CAMPAIGN_TYPE
    assert resolved.level is PlatformRateLevel.CAMPAIGN_TYPE


def test_the_system_rate_applies_when_nothing_more_specific_is_configured():
    resolved = resolve_platform_rate(system=SYSTEM)

    assert resolved.rate == SYSTEM
    assert resolved.level is PlatformRateLevel.SYSTEM


@pytest.mark.parametrize(
    ("line", "agency", "campaign_type", "expected_level"),
    [
        (None, AGENCY, None, PlatformRateLevel.AGENCY),
        (LINE, None, CAMPAIGN_TYPE, PlatformRateLevel.LINE),
        (None, None, CAMPAIGN_TYPE, PlatformRateLevel.CAMPAIGN_TYPE),
        (LINE, AGENCY, None, PlatformRateLevel.LINE),
    ],
)
def test_an_absent_level_is_skipped_not_treated_as_zero(
    line: Decimal | None, agency: Decimal | None, campaign_type: Decimal | None, expected_level: PlatformRateLevel
):
    resolved = resolve_platform_rate(system=SYSTEM, line=line, agency=agency, campaign_type=campaign_type)

    assert resolved.level is expected_level
    assert resolved.rate != Decimal("0")


def test_a_configured_zero_is_a_rate_and_wins():
    resolved = resolve_platform_rate(system=SYSTEM, line=Decimal("0.00"), agency=AGENCY)

    assert resolved.rate == Decimal("0.00")
    assert resolved.level is PlatformRateLevel.LINE


def test_the_system_value_is_required_input():
    with pytest.raises(TypeError):
        resolve_platform_rate()  # type: ignore[call-arg]


def test_the_system_value_is_whatever_the_data_says():
    assert resolve_platform_rate(system=Decimal("1.25")).rate == Decimal("1.25")
    assert resolve_platform_rate(system=Decimal("0.75")).rate == Decimal("0.75")


@pytest.mark.parametrize("field", ["system", "line", "agency", "campaign_type"])
def test_a_float_rate_is_refused(field: str):
    values: dict[str, object] = {"system": SYSTEM}
    values[field] = 1.0

    with pytest.raises(TypeError):
        resolve_platform_rate(**values)  # type: ignore[arg-type]


def test_a_resolved_rate_does_not_change_when_the_default_changes_afterwards():
    # Pure function over received values: an earlier result is a frozen value, and a later call with a
    # new default produces a new one. Freezing it in applied_rates at closing is task 6A, not tested here.
    before = resolve_platform_rate(system=Decimal("1.00"))
    after = resolve_platform_rate(system=Decimal("1.40"))

    assert before.rate == Decimal("1.00")
    assert after.rate == Decimal("1.40")
    with pytest.raises(dataclasses.FrozenInstanceError):
        before.rate = Decimal("9")  # type: ignore[misc]


def test_the_module_holds_no_numeric_constant():
    tree = ast.parse(Path(platform_rate.__file__).read_text())

    numbers = [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)
    ]

    assert numbers == []
