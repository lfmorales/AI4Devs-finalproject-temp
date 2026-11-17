from pathlib import Path

import pytest

from app.config import TEST_ISSUER, TEST_ISSUER_AUDIENCE, Settings, TokenIssuer


def test_settings_derive_cognito_issuer_and_jwks_url_from_region_and_user_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db:5432/adops360")
    monkeypatch.setenv("COGNITO_REGION", "eu-central-1")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "eu-central-1_Example1")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "example-client-id")

    settings = Settings()

    assert settings.cognito_issuer == "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_Example1"
    assert settings.cognito_jwks_url == f"{settings.cognito_issuer}/.well-known/jwks.json"


def test_settings_fail_fast_when_required_variables_are_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("DATABASE_URL", "COGNITO_REGION", "COGNITO_USER_POOL_ID", "COGNITO_CLIENT_ID"):
        monkeypatch.delenv(variable, raising=False)

    with pytest.raises(ValueError):
        Settings()


@pytest.fixture
def cognito_environment(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db:5432/adops360")
    monkeypatch.setenv("COGNITO_REGION", "eu-central-1")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "eu-central-1_Example1")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "example-client-id")
    monkeypatch.delenv("ENTRA_TENANT_ID", raising=False)
    monkeypatch.delenv("ENTRA_CLIENT_ID", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("TEST_ISSUER_PUBLIC_KEY_FILE", raising=False)
    return monkeypatch


def test_only_cognito_configured_gives_one_issuer(cognito_environment: pytest.MonkeyPatch) -> None:
    settings = Settings()

    assert settings.token_issuers == (
        TokenIssuer(
            kind="cognito",
            issuer="https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_Example1",
            audience="example-client-id",
            jwks_url="https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_Example1/.well-known/jwks.json",
            user_claim="sub",
            required_scope=None,
        ),
    )


def test_cognito_and_entra_configured_give_both_issuers_with_derived_values(
    cognito_environment: pytest.MonkeyPatch,
) -> None:
    cognito_environment.setenv("ENTRA_TENANT_ID", "tenant-de-prueba")
    cognito_environment.setenv("ENTRA_CLIENT_ID", "cliente-de-prueba")

    settings = Settings()

    assert [issuer.kind for issuer in settings.token_issuers] == ["cognito", "entra"]
    assert settings.token_issuers[1] == TokenIssuer(
        kind="entra",
        issuer="https://login.microsoftonline.com/tenant-de-prueba/v2.0",
        audience="cliente-de-prueba",
        jwks_url="https://login.microsoftonline.com/tenant-de-prueba/discovery/v2.0/keys",
        user_claim="oid",
        required_scope="access_as_user",
    )


@pytest.mark.parametrize(
    ("variable", "value", "missing"),
    [
        ("ENTRA_TENANT_ID", "tenant-de-prueba", "ENTRA_CLIENT_ID"),
        ("ENTRA_CLIENT_ID", "cliente-de-prueba", "ENTRA_TENANT_ID"),
    ],
)
def test_only_one_entra_variable_fails_at_startup_naming_the_missing_one(
    cognito_environment: pytest.MonkeyPatch, variable: str, value: str, missing: str
) -> None:
    cognito_environment.setenv(variable, value)

    with pytest.raises(ValueError, match=missing):
        Settings()


def test_no_entra_variable_leaves_entra_out_of_the_list(cognito_environment: pytest.MonkeyPatch) -> None:
    settings = Settings()

    assert [issuer.kind for issuer in settings.token_issuers] == ["cognito"]


def test_blank_entra_variables_count_as_absent(cognito_environment: pytest.MonkeyPatch) -> None:
    cognito_environment.setenv("ENTRA_TENANT_ID", "")
    cognito_environment.setenv("ENTRA_CLIENT_ID", "")

    assert [issuer.kind for issuer in Settings().token_issuers] == ["cognito"]


def test_the_cognito_issuer_and_jwks_url_are_unchanged_when_entra_is_configured(
    cognito_environment: pytest.MonkeyPatch,
) -> None:
    cognito_environment.setenv("ENTRA_TENANT_ID", "tenant-de-prueba")
    cognito_environment.setenv("ENTRA_CLIENT_ID", "cliente-de-prueba")

    settings = Settings()

    assert settings.cognito_issuer == "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_Example1"
    assert settings.cognito_jwks_url == f"{settings.cognito_issuer}/.well-known/jwks.json"


# --- The test issuer ---

ONLY_COGNITO = (
    TokenIssuer(
        kind="cognito",
        issuer="https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_Example1",
        audience="example-client-id",
        jwks_url="https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_Example1/.well-known/jwks.json",
        user_claim="sub",
        required_scope=None,
    ),
)


def test_the_test_issuer_constants_are_fixed() -> None:
    assert (TEST_ISSUER, TEST_ISSUER_AUDIENCE) == ("http://localhost/test-issuer/v2.0", "api://adops360-test-issuer")


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_the_key_in_development_and_test_adds_the_test_issuer_with_the_entra_rules(
    cognito_environment: pytest.MonkeyPatch, app_env: str
) -> None:
    cognito_environment.setenv("TEST_ISSUER_PUBLIC_KEY_FILE", "/keys/test-issuer-public.pem")
    cognito_environment.setenv("APP_ENV", app_env)

    assert Settings().token_issuers == (
        *ONLY_COGNITO,
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
    cognito_environment: pytest.MonkeyPatch, app_env: str | None
) -> None:
    cognito_environment.setenv("TEST_ISSUER_PUBLIC_KEY_FILE", "/keys/test-issuer-public.pem")
    if app_env is not None:
        cognito_environment.setenv("APP_ENV", app_env)

    with pytest.raises(ValueError) as raised:
        Settings()

    assert "TEST_ISSUER_PUBLIC_KEY_FILE" in str(raised.value)
    assert "APP_ENV" in str(raised.value)


@pytest.mark.parametrize("app_env", [None, "development", "test", "production", "anything"])
def test_without_the_key_app_env_leaves_the_issuer_list_as_before(
    cognito_environment: pytest.MonkeyPatch, app_env: str | None
) -> None:
    if app_env is not None:
        cognito_environment.setenv("APP_ENV", app_env)

    assert Settings().token_issuers == ONLY_COGNITO
