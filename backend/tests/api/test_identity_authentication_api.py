"""Through the real application: roles come from the database and a conflicting link answers 403."""

import time
from dataclasses import dataclass, replace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from app.application.services.authentication_service import AuthenticationService
from app.config import TokenIssuer
from app.domain.models.user import RoleName, User
from app.infrastructure.auth.composite_token_verifier import CompositeTokenVerifier
from app.infrastructure.auth.issuer_token_verifier import IssuerTokenVerifier
from app.main import create_app
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import get_authentication_service
from tests.fixtures.identity import InMemoryUserRepository, build_user

ENTRA = TokenIssuer(
    kind="entra",
    issuer="https://login.microsoftonline.com/tenant-de-prueba/v2.0",
    audience="cliente-de-prueba",
    jwks_url="https://login.microsoftonline.com/tenant-de-prueba/discovery/v2.0/keys",
    user_claim="oid",
    required_scope="access_as_user",
)
COGNITO = TokenIssuer(
    kind="cognito",
    issuer="https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_TestPool1",
    audience="cliente-cognito-de-prueba",
    jwks_url="https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_TestPool1/.well-known/jwks.json",
    user_claim="sub",
    required_scope=None,
)
ENTRA_KEY: RSAPrivateKey = rsa.generate_private_key(public_exponent=65537, key_size=2048)
COGNITO_KEY: RSAPrivateKey = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass(frozen=True)
class _SigningKey:
    key: RSAPublicKey


class _StaticKeys:
    def __init__(self, key: RSAPrivateKey) -> None:
        self._public_key = key.public_key()

    def get_signing_key_from_jwt(self, token: str) -> _SigningKey:
        return _SigningKey(key=self._public_key)


def _entra_token(subject: str = "sujeto-de-prueba", **extra_claims: object) -> str:
    now = int(time.time())
    claims = {
        "iss": ENTRA.issuer, "aud": ENTRA.audience, "iat": now, "exp": now + 3600, "oid": subject,
        "ver": "2.0", "scp": "access_as_user", "email": "ops@example.com", **extra_claims,
    }
    return jwt.encode(claims, ENTRA_KEY, algorithm="RS256", headers={"kid": "test-kid"})


def _cognito_token(**extra_claims: object) -> str:
    now = int(time.time())
    claims = {
        "iss": COGNITO.issuer, "aud": COGNITO.audience, "iat": now, "exp": now + 3600, "sub": "sujeto-cognito",
        "token_use": "id", "email": "ops@example.com", "email_verified": True, **extra_claims,
    }
    return jwt.encode(claims, COGNITO_KEY, algorithm="RS256", headers={"kid": "test-kid"})


def _client(users: list[User]) -> TestClient:
    router = APIRouter()

    @router.get("/probe/operations")
    def operations_probe(user: User = Depends(require_roles(RoleName.OPERATIONS))) -> dict[str, str]:
        return {"email": user.email}

    @router.get("/probe/finance")
    def finance_probe(user: User = Depends(require_roles(RoleName.FINANCE))) -> dict[str, str]:
        return {"email": user.email}

    app = create_app()
    app.include_router(router)
    service = AuthenticationService(
        token_verifier=CompositeTokenVerifier(
            {
                ENTRA.issuer: IssuerTokenVerifier(ENTRA, _StaticKeys(ENTRA_KEY)),
                COGNITO.issuer: IssuerTokenVerifier(COGNITO, _StaticKeys(COGNITO_KEY)),
            }
        ),
        user_repository=InMemoryUserRepository(users),
    )
    app.dependency_overrides[get_authentication_service] = lambda: service
    return TestClient(app)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_an_entra_token_claiming_finance_is_authorised_with_the_roles_stored_in_the_database() -> None:
    client = _client([build_user(email="ops@example.com", roles=[RoleName.OPERATIONS])])
    token = _entra_token(roles=["finance"])

    assert client.get("/probe/operations", headers=_bearer(token)).status_code == 200
    forbidden = client.get("/probe/finance", headers=_bearer(token))
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "missing_role"


def test_a_conflicting_link_answers_403_with_its_code() -> None:
    linked_elsewhere = replace(
        build_user(email="ops@example.com"), identity_issuer=ENTRA.issuer, identity_subject="otro-sujeto"
    )
    client = _client([linked_elsewhere])

    response = client.get("/probe/operations", headers=_bearer(_entra_token(subject="sujeto-de-prueba")))

    assert response.status_code == 403
    assert response.json()["code"] == "identity_link_conflict"


def test_a_cognito_token_is_authorised_with_the_roles_stored_in_the_database() -> None:
    client = _client([build_user(email="ops@example.com", roles=[RoleName.OPERATIONS])])
    token = _cognito_token(**{"custom:roles": "finance"})

    assert client.get("/probe/operations", headers=_bearer(token)).status_code == 200
    assert client.get("/probe/finance", headers=_bearer(token)).status_code == 403


def test_a_user_without_roles_is_forbidden_on_every_protected_route() -> None:
    client = _client([build_user(email="ops@example.com", roles=[])])
    token = _entra_token(roles=["operations", "finance"])

    for path in ("/probe/operations", "/probe/finance"):
        response = client.get(path, headers=_bearer(token))
        assert response.status_code == 403
        assert response.json()["code"] == "missing_role"


def test_two_stored_roles_compose() -> None:
    client = _client([build_user(email="ops@example.com", roles=[RoleName.OPERATIONS, RoleName.FINANCE])])
    token = _entra_token()

    assert client.get("/probe/operations", headers=_bearer(token)).status_code == 200
    assert client.get("/probe/finance", headers=_bearer(token)).status_code == 200
