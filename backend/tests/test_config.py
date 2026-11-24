from pathlib import Path
from typing import get_args

import pytest

from app.config import TEST_ISSUER, TEST_ISSUER_AUDIENCE, Settings, TokenIssuer


def test_settings_fail_fast_when_required_variables_are_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("DATABASE_URL", "ENTRA_TENANT_ID", "ENTRA_CLIENT_ID"):
        monkeypatch.delenv(variable, raising=False)

    with pytest.raises(ValueError):
        Settings()


@pytest.fixture
def entra_environment(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db:5432/adops360")
    monkeypatch.setenv("ENTRA_TENANT_ID", "tenant-de-prueba")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cliente-de-prueba")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("TEST_ISSUER_PUBLIC_KEY_FILE", raising=False)
    return monkeypatch


ONLY_ENTRA = (
    TokenIssuer(
        kind="entra",
        issuer="https://login.microsoftonline.com/tenant-de-prueba/v2.0",
        audience="cliente-de-prueba",
        jwks_url="https://login.microsoftonline.com/tenant-de-prueba/discovery/v2.0/keys",
        user_claim="oid",
        required_scope="access_as_user",
    ),
)


def test_entra_configured_gives_its_issuer_with_derived_values(entra_environment: pytest.MonkeyPatch) -> None:
    assert Settings().token_issuers == ONLY_ENTRA


@pytest.mark.parametrize(
    ("variable", "missing"),
    [
        ("ENTRA_TENANT_ID", "ENTRA_CLIENT_ID"),
        ("ENTRA_CLIENT_ID", "ENTRA_TENANT_ID"),
    ],
)
def test_only_one_entra_variable_fails_at_startup_naming_the_missing_one(
    entra_environment: pytest.MonkeyPatch, variable: str, missing: str
) -> None:
    entra_environment.delenv(missing)

    with pytest.raises(ValueError, match=missing):
        Settings()


def test_the_settings_have_no_cognito_setting() -> None:
    assert [name for name in Settings.model_fields if "cognito" in name] == []


def test_the_only_issuer_kind_is_entra() -> None:
    assert get_args(TokenIssuer.__annotations__["kind"]) == ("entra",)


# --- The test issuer ---

def test_the_test_issuer_constants_are_fixed() -> None:
    assert (TEST_ISSUER, TEST_ISSUER_AUDIENCE) == ("http://localhost/test-issuer/v2.0", "api://adops360-test-issuer")


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_the_key_in_development_and_test_adds_the_test_issuer_with_the_entra_rules(
    entra_environment: pytest.MonkeyPatch, app_env: str
) -> None:
    entra_environment.setenv("TEST_ISSUER_PUBLIC_KEY_FILE", "/keys/test-issuer-public.pem")
    entra_environment.setenv("APP_ENV", app_env)

    assert Settings().token_issuers == (
        *ONLY_ENTRA,
        TokenIssuer(
            kind="entra",
            issuer="http://localhost/test-issuer/v2.0",
            audience="api://adops360-test-issuer",
            jwks_url=None,
            user_claim="oid",
            required_scope="access_as_user",
            public_key_file=Path("/keys/test-issuer-public.pem"),
        ),
    )


@pytest.mark.parametrize(
    "app_env", [None, "production", "Development", " development", "test ", "staging"],
    ids=["absent", "production", "capitalised", "leading-space", "trailing-space", "other"],
)
def test_the_key_with_any_other_app_env_fails_naming_both_variables(
    entra_environment: pytest.MonkeyPatch, app_env: str | None
) -> None:
    entra_environment.setenv("TEST_ISSUER_PUBLIC_KEY_FILE", "/keys/test-issuer-public.pem")
    if app_env is not None:
        entra_environment.setenv("APP_ENV", app_env)

    with pytest.raises(ValueError) as raised:
        Settings()

    assert "TEST_ISSUER_PUBLIC_KEY_FILE" in str(raised.value)
    assert "APP_ENV" in str(raised.value)


@pytest.mark.parametrize("app_env", [None, "development", "test", "production", "anything"])
def test_without_the_key_app_env_leaves_the_issuer_list_as_before(
    entra_environment: pytest.MonkeyPatch, app_env: str | None
) -> None:
    if app_env is not None:
        entra_environment.setenv("APP_ENV", app_env)

    assert Settings().token_issuers == ONLY_ENTRA


def test_the_settings_load_without_the_equativ_credentials(entra_environment: pytest.MonkeyPatch) -> None:
    entra_environment.delenv("EQUATIV_CLIENT_ID", raising=False)
    entra_environment.delenv("EQUATIV_CLIENT_SECRET", raising=False)

    settings = Settings()

    assert (settings.equativ_client_id, settings.equativ_client_secret) == (None, None)


def test_the_equativ_secret_is_read_as_a_secret_that_no_repr_reveals(entra_environment: pytest.MonkeyPatch) -> None:
    entra_environment.setenv("EQUATIV_CLIENT_ID", "synthetic-equativ-client-id")
    entra_environment.setenv("EQUATIV_CLIENT_SECRET", "synthetic-equativ-client-secret")

    settings = Settings()

    assert settings.equativ_client_id == "synthetic-equativ-client-id"
    assert settings.equativ_client_secret is not None
    assert settings.equativ_client_secret.get_secret_value() == "synthetic-equativ-client-secret"
    assert "synthetic-equativ-client-secret" not in repr(settings)


def test_the_api_starts_and_answers_without_the_equativ_credentials(entra_environment: pytest.MonkeyPatch) -> None:
    import asyncio

    import httpx

    from app.config import get_settings
    from app.main import create_app

    entra_environment.delenv("EQUATIV_CLIENT_ID", raising=False)
    entra_environment.delenv("EQUATIV_CLIENT_SECRET", raising=False)
    get_settings.cache_clear()

    async def _health() -> int:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://backend") as client:
            return (await client.get("/health")).status_code

    assert asyncio.run(_health()) == 200
