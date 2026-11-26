"""The platform rate is data: no module of the application holds a platform rate as a constant."""

import ast
import re
from pathlib import Path

import pytest

import app

APP_ROOT = Path(app.__file__).parent
ONE_EURO = re.compile(r"^1(\.0+)?$")


def _modules() -> list[Path]:
    return sorted(APP_ROOT.rglob("*.py"))


def test_there_are_modules_to_scan():
    assert len(_modules()) > 100


# Why this exception exists: a warning threshold may be one euro without being a rate. `MARGIN_CHANGE_TOLERANCE` of
# `app/domain/services/closed_flight.py` is the 1.00 € a closed flight's margin must move to raise «Cambió tras el
# cierre»; no cost is computed from it. Only a `Decimal` assigned on its own to a name ending in `_TOLERANCE` passes;
# `test_only_a_tolerance_assigned_on_its_own_may_be_one_euro` checks that nothing else does.
def _tolerances(tree: ast.AST) -> set[int]:
    """The ids of the values assigned to a name ending in `_TOLERANCE`: a threshold in euros, never a rate."""
    return {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.endswith("_TOLERANCE")
    }


def _one_euro_decimals(source: str) -> list[int]:
    tree = ast.parse(source)
    tolerances = _tolerances(tree)
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "Decimal"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and ONE_EURO.match(node.args[0].value)
        and id(node) not in tolerances
    ]


@pytest.mark.parametrize("path", _modules(), ids=lambda path: str(path.relative_to(APP_ROOT)))
def test_no_module_builds_a_decimal_of_one_euro_as_a_rate(path: Path):
    assert _one_euro_decimals(path.read_text()) == []


def test_only_a_tolerance_assigned_on_its_own_may_be_one_euro():
    source = (
        'MARGIN_CHANGE_TOLERANCE = Decimal("1.00")\n'
        'RATE = Decimal("1.00")\n'
        'A_TOLERANCE = Decimal("1.00") * rate\n'
        'cost = impressions * Decimal("1")\n'
    )

    assert _one_euro_decimals(source) == [2, 3, 4]


@pytest.mark.parametrize("path", _modules(), ids=lambda path: str(path.relative_to(APP_ROOT)))
def test_no_name_holding_a_platform_rate_is_assigned_a_number(path: Path):
    tree = ast.parse(path.read_text())
    offenders = []
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = [target for target in node.targets if isinstance(target, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        value = getattr(node, "value", None)
        if isinstance(value, ast.Constant) and isinstance(value.value, (int, float, str)) and any(
            "platform_rate" in target.id.lower() or "default_rate" in target.id.lower() for target in targets
        ):
            offenders.append(node.lineno)

    assert offenders == []
