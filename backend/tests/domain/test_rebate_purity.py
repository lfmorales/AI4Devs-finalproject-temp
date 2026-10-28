"""The rebate engine is pure: no float, no persistence or web framework, Decimal throughout."""

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.services import rebate_brackets, rebate_engine, rebate_ladder
from app.domain.services.rebate_engine import calculate_rebates
from app.domain.value_objects import rebate
from tests.domain.test_rebate_engine import AS_OF, group_schedule, month_flight

REBATE_MODULES = (rebate, rebate_ladder, rebate_brackets, rebate_engine)
FORBIDDEN_IMPORTS = {"sqlalchemy", "fastapi", "starlette", "pydantic", "alembic"}


def _tree(module: object) -> ast.AST:
    return ast.parse(Path(module.__file__).read_text())  # type: ignore[attr-defined]


@pytest.mark.parametrize("module", REBATE_MODULES)
def test_no_rebate_module_uses_float(module: object):
    tree = _tree(module)

    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, float)]
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "float"]


@pytest.mark.parametrize("module", REBATE_MODULES)
def test_no_rebate_module_imports_a_framework(module: object):
    imported: set[str] = set()
    for node in ast.walk(_tree(module)):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert not imported & FORBIDDEN_IMPORTS


def test_every_amount_the_engine_returns_is_a_decimal():
    flights = [month_flight(1, 3, "90000"), month_flight(2, 4, "30000")]

    for result in calculate_rebates([group_schedule()], flights, AS_OF):
        amounts = [result.effective_rate, result.position_before, result.position_after, result.rebate]
        for charge in result.charges:
            amounts += [charge.lower, charge.rate, charge.amount, charge.rebate]
            amounts += [] if charge.upper is None else [charge.upper]
        assert all(isinstance(amount, Decimal) for amount in amounts)
