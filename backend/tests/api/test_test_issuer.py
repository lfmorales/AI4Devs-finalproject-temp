"""The test issuer through the real application: active only in development and test, and the backend
refuses to start when its key is set outside them or cannot be used."""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import ClassVar

import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi.testclient import TestClient

from app.config import TEST_ISSUER, TEST_ISSUER_AUDIENCE, get_settings
from app.domain.models.user import User
from app.main import create_app
from app.presentation.dependencies import providers
from app.presentation.dependencies.providers import get_db_session
from tests.fixtures.identity import InMemoryUserRepository, build_user
from tests.fixtures.identity_tokens import (
    OTHER_TEST_KEY,
    TEST_EMAIL,
    TEST_KEY,
    bearer,
    entra_token,
)
from tests.fixtures.key_files import (
    UNUSABLE_KEY_FILE_IDS,
    UNUSABLE_KEY_FILES,
    write_public_pem,
)

PROTECTED_PATH = "/users/me"


class _RecordingUserRepository(InMemoryUserRepository):
    """Replaces SqlAlchemyUserRepository: one registered user, and every lookup recorded."""

    users: ClassVar[list[User]] = []
    lookups: ClassVar[list[str]] = []

    def __init__(self, session: object) -> None:
        super().__init__(_RecordingUserRepository.users)

    def get_by_identity(self, issuer: str, subject: str) -> User | None:
        _RecordingUserRepository.lookups.append(f"{issuer}|{subject}")
        return super().get_by_identity(issuer, subject)

    def get_by_email(self, email: str) -> User | None:
        _RecordingUserRepository.lookups.append(email)
        return super().get_by_email(email)


@pytest.fixture(autouse=True)
def fresh_configuration(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Each case builds its own settings and verifier from its own environment, and leaves none behind."""
    get_settings.cache_clear()
    providers._token_verifier.cache_clear()
    monkeypatch.setenv("COGNITO_REGION", "eu-central-1")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "eu-central-1_Example1")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "example-client-id")
    for variable in ("ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "APP_ENV", "TEST_ISSUER_PUBLIC_KEY_FILE"):
        monkeypatch.delenv(variable, raising=False)
    _RecordingUserRepository.users = [build_user(email=TEST_EMAIL)]
    _RecordingUserRepository.lookups = []
    monkeypatch.setattr(providers, "SqlAlchemyUserRepository", _RecordingUserRepository)
    yield
    get_settings.cache_clear()
    providers._token_verifier.cache_clear()


@pytest.fixture
def public_key_file(tmp_path: Path) -> Path:
    return write_public_pem(tmp_path / "test-issuer-public.pem", TEST_KEY)


def _app() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: None
    return TestClient(app)


def _test_issuer_token(claims: dict[str, object] | None = None, key: RSAPrivateKey = TEST_KEY) -> str:
    return entra_token(claims, iss=TEST_ISSUER, aud=TEST_ISSUER_AUDIENCE, key=key)


# --- Accepted only in development and test ---


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_a_test_issuer_token_reaches_a_protected_route(
    monkeypatch: pytest.MonkeyPatch, public_key_file: Path, app_env: str
) -> None:
    monkeypatch.setenv("TEST_ISSUER_PUBLIC_KEY_FILE", str(public_key_file))
    monkeypatch.setenv("APP_ENV", app_env)

    with _app() as client:
        response = client.get(PROTECTED_PATH, headers=bearer(_test_issuer_token()))

    assert response.status_code == 200


@pytest.mark.parametrize("app_env", ["production", None, "Development", "staging"], ids=["production", "absent", "Development", "other"])
def test_the_backend_does_not_start_with_the_test_key_outside_development_and_test(
    monkeypatch: pytest.MonkeyPatch, public_key_file: Path, app_env: str | None
) -> None:
    monkeypatch.setenv("TEST_ISSUER_PUBLIC_KEY_FILE", str(public_key_file))
    if app_env is not None:
        monkeypatch.setenv("APP_ENV", app_env)

    with pytest.raises(ValueError) as raised, _app():
        pass

    assert "TEST_ISSUER_PUBLIC_KEY_FILE" in str(raised.value)
    assert "APP_ENV" in str(raised.value)


@pytest.mark.parametrize("make_file", UNUSABLE_KEY_FILES, ids=UNUSABLE_KEY_FILE_IDS)
def test_the_backend_does_not_start_with_an_unusable_test_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, make_file: Callable[[Path], Path]
) -> None:
    monkeypatch.setenv("TEST_ISSUER_PUBLIC_KEY_FILE", str(make_file(tmp_path)))
    monkeypatch.setenv("APP_ENV", "development")

    with pytest.raises(ValueError) as raised, _app():
        pass

    assert "TEST_ISSUER_PUBLIC_KEY_FILE" in str(raised.value)


def test_without_the_key_a_test_issuer_token_is_401_and_no_user_is_looked_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")

    with _app() as client:
        response = client.get(PROTECTED_PATH, headers=bearer(_test_issuer_token()))

    assert response.status_code == 401
    assert _RecordingUserRepository.lookups == []


def test_without_the_key_production_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")

    with _app() as client:
        assert client.get("/health").status_code == 200


# --- The Entra rules ---


@pytest.mark.parametrize(
    ("claims", "key"),
    [
        ({"scp": "openid profile"}, TEST_KEY),
        ({"oid": None}, TEST_KEY),
        ({"ver": "1.0"}, TEST_KEY),
        (None, OTHER_TEST_KEY),
    ],
    ids=["without-scope", "without-oid", "other-version", "other-key"],
)
def test_a_test_issuer_token_breaking_the_entra_rules_is_401(
    monkeypatch: pytest.MonkeyPatch, public_key_file: Path, claims: dict[str, object] | None, key: RSAPrivateKey
) -> None:
    monkeypatch.setenv("TEST_ISSUER_PUBLIC_KEY_FILE", str(public_key_file))
    monkeypatch.setenv("APP_ENV", "development")

    with _app() as client:
        response = client.get(PROTECTED_PATH, headers=bearer(_test_issuer_token(claims, key)))

    assert response.status_code == 401
