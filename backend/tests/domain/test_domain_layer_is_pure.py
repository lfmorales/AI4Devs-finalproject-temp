"""The dependency rule: nothing under `domain/` imports a persistence, web or infrastructure module."""

import ast
from pathlib import Path

import pytest

import app.domain

DOMAIN_ROOT = Path(app.domain.__file__).parent
FORBIDDEN_ROOTS = {"sqlalchemy", "alembic", "fastapi", "starlette", "pydantic", "psycopg", "httpx"}
FORBIDDEN_APP_LAYERS = ("app.infrastructure", "app.presentation", "app.application")


def _domain_files() -> list[Path]:
    return sorted(path for path in DOMAIN_ROOT.rglob("*.py"))


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_there_are_domain_modules_to_check():
    assert len(_domain_files()) > 20


@pytest.mark.parametrize("path", _domain_files(), ids=lambda path: str(path.relative_to(DOMAIN_ROOT)))
def test_a_domain_module_imports_no_framework_and_no_outer_layer(path: Path):
    imported = _imports(path)

    assert not {name for name in imported if name.split(".")[0] in FORBIDDEN_ROOTS}
    assert not {name for name in imported if name.startswith(FORBIDDEN_APP_LAYERS)}
