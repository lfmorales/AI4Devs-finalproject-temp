"""Entra is the one real issuer: without its tenant or its client the backend does not start, and the error names
the variable that is missing. tests/conftest.py sets both to example values before each case."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

ENTRA_VARIABLES = ("ENTRA_TENANT_ID", "ENTRA_CLIENT_ID")


def _start_the_backend() -> None:
    with TestClient(create_app()):
        pass


@pytest.mark.parametrize("value", [None, "", "   "], ids=["absent", "empty", "blank"])
@pytest.mark.parametrize("variable", ENTRA_VARIABLES)
def test_the_backend_does_not_start_without_an_entra_variable_and_names_it(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(variable)
    else:
        monkeypatch.setenv(variable, value)
    (other,) = (name for name in ENTRA_VARIABLES if name != variable)

    with pytest.raises(ValueError) as raised:
        _start_the_backend()

    assert variable in str(raised.value)
    assert other not in str(raised.value)


def test_the_backend_does_not_start_without_both_and_names_both(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ENTRA_VARIABLES:
        monkeypatch.delenv(variable)

    with pytest.raises(ValueError) as raised:
        _start_the_backend()

    assert all(variable in str(raised.value) for variable in ENTRA_VARIABLES)


def test_the_backend_starts_with_both_set() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
