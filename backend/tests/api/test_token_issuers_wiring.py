"""The verifier built by providers.py reflects the configured issuers, and an unknown issuer never reaches the users."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from fastapi.testclient import TestClient

from app.config import TEST_ISSUER, TEST_ISSUER_AUDIENCE, get_settings
from app.domain.exceptions import InvalidIdentityTokenError
from app.domain.models.user import User
from app.main import create_app
from app.presentation.dependencies import providers
from app.presentation.dependencies.providers import get_db_session
from tests.fixtures.identity_tokens import (
    OTHER_TEST_KEY,
    TEST_KEY,
    SigningKey,
    entra_token,
)
from tests.fixtures.key_files import write_public_pem

ENTRA_ISSUER = "https://login.microsoftonline.com/tenant-de-prueba/v2.0"
ENTRA_AUDIENCE = "cliente-de-prueba"

class _KeysByUrl:
    """Stands in for the cached key provider: no network, the keys depend on the URL the provider configured."""

    _PUBLIC_KEYS: dict[str, RSAPublicKey] = {}

    def __init__(self, jwks_url: str) -> None:
        self._public_key = self._PUBLIC_KEYS[jwks_url]

    def get_signing_key_from_jwt(self, token: str) -> SigningKey:
        return SigningKey(key=self._public_key)


def _test_issuer_token(key: RSAPrivateKey = OTHER_TEST_KEY) -> str:
    return entra_token({"oid": "sujeto-emisor-de-pruebas"}, iss=TEST_ISSUER, aud=TEST_ISSUER_AUDIENCE, key=key)


def _entra_token(key: RSAPrivateKey = TEST_KEY) -> str:
    return entra_token({"oid": "sujeto-entra"}, iss=ENTRA_ISSUER, aud=ENTRA_AUDIENCE, key=key)


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Any]:
    """Sets the issuer environment, then rebuilds the cached settings and verifier around it."""
    _KeysByUrl._PUBLIC_KEYS = {
        "https://login.microsoftonline.com/tenant-de-prueba/discovery/v2.0/keys": TEST_KEY.public_key(),
    }
    monkeypatch.setattr(providers, "CachedJwksKeyProvider", _KeysByUrl)

    def _apply(with_test_issuer: bool) -> None:
        monkeypatch.setenv("ENTRA_TENANT_ID", "tenant-de-prueba")
        monkeypatch.setenv("ENTRA_CLIENT_ID", ENTRA_AUDIENCE)
        if with_test_issuer:
            public_key_file = write_public_pem(tmp_path / "test-issuer-public.pem", OTHER_TEST_KEY)
            monkeypatch.setenv("TEST_ISSUER_PUBLIC_KEY_FILE", str(public_key_file))
            monkeypatch.setenv("APP_ENV", "development")
        get_settings.cache_clear()
        providers._token_verifier.cache_clear()

    yield _apply
    get_settings.cache_clear()
    providers._token_verifier.cache_clear()


def test_with_both_issuers_configured_each_accepts_its_own_token(configure: Any) -> None:
    configure(with_test_issuer=True)

    verifier = providers._token_verifier()

    assert verifier.verify(_test_issuer_token()).issuer == TEST_ISSUER
    assert verifier.verify(_entra_token()).issuer == ENTRA_ISSUER


def test_with_both_issuers_configured_a_token_signed_for_the_other_issuer_is_not_accepted(configure: Any) -> None:
    configure(with_test_issuer=True)
    verifier = providers._token_verifier()

    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify(_test_issuer_token(key=TEST_KEY))
    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify(_entra_token(key=OTHER_TEST_KEY))


class _RecordingUserRepository:
    calls: list[str] = []

    def __init__(self, session: object) -> None:
        pass

    def get_by_identity(self, issuer: str, subject: str) -> User | None:
        _RecordingUserRepository.calls.append(f"{issuer}|{subject}")
        return None

    def get_by_email(self, email: str) -> User | None:
        _RecordingUserRepository.calls.append(email)
        return None


def test_a_token_of_an_unknown_issuer_gives_401_and_the_user_repository_is_not_queried(
    configure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(with_test_issuer=False)
    _RecordingUserRepository.calls = []
    monkeypatch.setattr(providers, "SqlAlchemyUserRepository", _RecordingUserRepository)
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: None
    unknown_issuer_token = jwt.encode(
        {"iss": "https://emisor-desconocido.example.com", "aud": "otra", "sub": "x", "email": "ops@example.com"},
        OTHER_TEST_KEY,
        algorithm="RS256",
    )

    response = TestClient(app).get(
        "/campaign-lines/unmapped", headers={"Authorization": f"Bearer {unknown_issuer_token}"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"
    assert _RecordingUserRepository.calls == []


def test_the_recording_repository_does_see_the_query_of_a_token_of_a_configured_issuer(
    configure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control for the test above: the double does record calls, so an empty list means something."""
    configure(with_test_issuer=False)
    _RecordingUserRepository.calls = []
    monkeypatch.setattr(providers, "SqlAlchemyUserRepository", _RecordingUserRepository)
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: None

    response = TestClient(app).get("/campaign-lines/unmapped", headers={"Authorization": f"Bearer {_entra_token()}"})

    assert response.status_code == 403
    assert _RecordingUserRepository.calls == [f"{ENTRA_ISSUER}|sujeto-entra", "ops@example.com"]
