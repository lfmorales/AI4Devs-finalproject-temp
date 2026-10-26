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


@pytest.mark.parametrize("path", _modules(), ids=lambda path: str(path.relative_to(APP_ROOT)))
def test_no_module_builds_a_decimal_of_one_euro_as_a_rate(path: Path):
    tree = ast.parse(path.read_text())
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "Decimal"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and ONE_EURO.match(node.args[0].value)
    ]

    assert offenders == []


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
