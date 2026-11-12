"""The verifier built by providers.py reflects the configured issuers, and an unknown issuer never reaches the users."""

import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.domain.exceptions import InvalidIdentityTokenError
from app.domain.models.user import User
from app.main import create_app
from app.presentation.dependencies import providers
from app.presentation.dependencies.providers import get_db_session

COGNITO_ISSUER = "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_Example1"
ENTRA_ISSUER = "https://login.microsoftonline.com/tenant-de-prueba/v2.0"
COGNITO_AUDIENCE = "example-client-id"
ENTRA_AUDIENCE = "cliente-de-prueba"

COGNITO_KEY: RSAPrivateKey = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ENTRA_KEY: RSAPrivateKey = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass(frozen=True)
class _SigningKey:
    key: RSAPublicKey


class _KeysByUrl:
    """Stands in for PyJWKClient: no network, the keys depend on the URL the provider configured."""

    _PUBLIC_KEYS: dict[str, RSAPublicKey] = {}

    def __init__(self, jwks_url: str) -> None:
        self._public_key = self._PUBLIC_KEYS[jwks_url]

    def get_signing_key_from_jwt(self, token: str) -> _SigningKey:
        return _SigningKey(key=self._public_key)


def _cognito_token(key: RSAPrivateKey = COGNITO_KEY) -> str:
    now = int(time.time())
    claims = {
        "iss": COGNITO_ISSUER, "aud": COGNITO_AUDIENCE, "iat": now, "exp": now + 3600, "sub": "sujeto-cognito",
        "token_use": "id", "email": "ops@example.com", "email_verified": True,
    }
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-kid"})


def _entra_token(key: RSAPrivateKey = ENTRA_KEY) -> str:
    now = int(time.time())
    claims = {
        "iss": ENTRA_ISSUER, "aud": ENTRA_AUDIENCE, "iat": now, "exp": now + 3600, "oid": "sujeto-entra",
        "ver": "2.0", "scp": "access_as_user", "email": "ops@example.com",
    }
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-kid"})


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Sets the issuer environment, then rebuilds the cached settings and verifier around it."""
    _KeysByUrl._PUBLIC_KEYS = {
        f"{COGNITO_ISSUER}/.well-known/jwks.json": COGNITO_KEY.public_key(),
        "https://login.microsoftonline.com/tenant-de-prueba/discovery/v2.0/keys": ENTRA_KEY.public_key(),
    }
    monkeypatch.setattr("app.infrastructure.auth.issuer_token_verifier.PyJWKClient", _KeysByUrl)

    def _apply(with_entra: bool) -> None:
        monkeypatch.setenv("COGNITO_REGION", "eu-central-1")
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "eu-central-1_Example1")
        monkeypatch.setenv("COGNITO_CLIENT_ID", COGNITO_AUDIENCE)
        if with_entra:
            monkeypatch.setenv("ENTRA_TENANT_ID", "tenant-de-prueba")
            monkeypatch.setenv("ENTRA_CLIENT_ID", ENTRA_AUDIENCE)
        else:
            monkeypatch.delenv("ENTRA_TENANT_ID", raising=False)
            monkeypatch.delenv("ENTRA_CLIENT_ID", raising=False)
        get_settings.cache_clear()
        providers._token_verifier.cache_clear()

    yield _apply
    get_settings.cache_clear()
    providers._token_verifier.cache_clear()


def test_with_only_cognito_configured_a_cognito_token_is_accepted_and_an_entra_one_is_not(configure: Any) -> None:
    configure(with_entra=False)

    verifier = providers._token_verifier()

    assert verifier.verify(_cognito_token()).issuer == COGNITO_ISSUER
    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify(_entra_token())


def test_with_both_issuers_configured_each_accepts_its_own_token(configure: Any) -> None:
    configure(with_entra=True)

    verifier = providers._token_verifier()

    assert verifier.verify(_cognito_token()).issuer == COGNITO_ISSUER
    assert verifier.verify(_entra_token()).issuer == ENTRA_ISSUER


def test_with_entra_configured_a_token_signed_for_the_other_issuer_is_not_accepted(configure: Any) -> None:
    configure(with_entra=True)
    verifier = providers._token_verifier()

    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify(_cognito_token(key=ENTRA_KEY))
    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify(_entra_token(key=COGNITO_KEY))


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
    configure(with_entra=True)
    _RecordingUserRepository.calls = []
    monkeypatch.setattr(providers, "SqlAlchemyUserRepository", _RecordingUserRepository)
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: None
    unknown_issuer_token = jwt.encode(
        {"iss": "https://emisor-desconocido.example.com", "aud": "otra", "sub": "x", "email": "ops@example.com"},
        COGNITO_KEY,
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
    configure(with_entra=True)
    _RecordingUserRepository.calls = []
    monkeypatch.setattr(providers, "SqlAlchemyUserRepository", _RecordingUserRepository)
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: None

    response = TestClient(app).get("/campaign-lines/unmapped", headers={"Authorization": f"Bearer {_cognito_token()}"})

    assert response.status_code == 403
    assert _RecordingUserRepository.calls == [f"{COGNITO_ISSUER}|sujeto-cognito", "ops@example.com"]
