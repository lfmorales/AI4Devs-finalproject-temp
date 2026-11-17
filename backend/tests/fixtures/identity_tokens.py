"""Test keys, a static key provider and token builders shared by the identity tests.

No network: tokens are signed with keys generated per run and verified against
`StaticKeys`, which stands in for the key provider of `IssuerTokenVerifier`.
"""

import time
from collections.abc import Mapping
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from app.config import TokenIssuer


def _generate_private_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


TEST_KEY: RSAPrivateKey = _generate_private_key()
OTHER_TEST_KEY: RSAPrivateKey = _generate_private_key()

ENTRA = TokenIssuer(
    kind="entra",
    issuer="https://login.microsoftonline.com/tenant-de-prueba/v2.0",
    audience="cliente-de-prueba",
    jwks_url="https://login.microsoftonline.com/tenant-de-prueba/discovery/v2.0/keys",
    user_claim="oid",
    required_scope="access_as_user",
)
ENTRA_TENANT = "tenant-de-prueba"
TEST_EMAIL = "ops@example.com"


@dataclass(frozen=True)
class SigningKey:
    key: RSAPublicKey


class StaticKeys:
    """Stands in for the key provider: returns one public key, or raises a given error."""

    def __init__(self, public_key: RSAPublicKey, error: Exception | None = None) -> None:
        self._public_key = public_key
        self._error = error

    def get_signing_key_from_jwt(self, token: str) -> SigningKey:
        if self._error is not None:
            raise self._error
        return SigningKey(key=self._public_key)


def _sign(claims: dict[str, object], key: RSAPrivateKey) -> str:
    present = {name: value for name, value in claims.items() if value is not None}
    return jwt.encode(present, key, algorithm="RS256", headers={"kid": "test-kid"})


def entra_token(
    claims: Mapping[str, object] | None = None,
    *,
    iss: str = ENTRA.issuer,
    aud: str = ENTRA.audience,
    key: RSAPrivateKey = TEST_KEY,
) -> str:
    """An Entra version 2 access token. `claims` overrides any default claim, and a None value removes it."""
    now = int(time.time())
    defaults: dict[str, object] = {
        "iss": iss,
        "aud": aud,
        "iat": now,
        "exp": now + 3600,
        "oid": "sujeto-de-prueba",
        "tid": ENTRA_TENANT,
        "ver": "2.0",
        "scp": "access_as_user",
        "email": TEST_EMAIL,
    }
    return _sign({**defaults, **(claims or {})}, key)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Cognito: removed with the Cognito issuer in task 21.7 ---

COGNITO_TEST_KEY: RSAPrivateKey = _generate_private_key()

COGNITO = TokenIssuer(
    kind="cognito",
    issuer="https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_TestPool1",
    audience="cliente-cognito-de-prueba",
    jwks_url="https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_TestPool1/.well-known/jwks.json",
    user_claim="sub",
    required_scope=None,
)


def cognito_token(
    claims: Mapping[str, object] | None = None,
    *,
    iss: str = COGNITO.issuer,
    aud: str = COGNITO.audience,
    key: RSAPrivateKey = COGNITO_TEST_KEY,
) -> str:
    """A Cognito identity token, as the identity tests built it before; `claims` overrides or removes as above."""
    now = int(time.time())
    defaults: dict[str, object] = {
        "iss": iss,
        "aud": aud,
        "iat": now,
        "exp": now + 3600,
        "sub": "sujeto-cognito",
        "token_use": "id",
        "email": TEST_EMAIL,
        "email_verified": True,
    }
    return _sign({**defaults, **(claims or {})}, key)
