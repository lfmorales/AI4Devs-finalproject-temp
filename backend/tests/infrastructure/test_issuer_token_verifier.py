"""One verifier per configured issuer: the common rules, then the rules of the issuer's kind."""

import time
from dataclasses import dataclass

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from jwt import PyJWKClientConnectionError

from app.config import TokenIssuer
from app.domain.exceptions import IdentityProviderUnavailableError, InvalidIdentityTokenError
from app.infrastructure.auth.issuer_token_verifier import IssuerTokenVerifier

COGNITO = TokenIssuer(
    kind="cognito",
    issuer="https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_TestPool1",
    audience="cliente-cognito-de-prueba",
    jwks_url="https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_TestPool1/.well-known/jwks.json",
    user_claim="sub",
    required_scope=None,
)
ENTRA = TokenIssuer(
    kind="entra",
    issuer="https://login.microsoftonline.com/tenant-de-prueba/v2.0",
    audience="cliente-de-prueba",
    jwks_url="https://login.microsoftonline.com/tenant-de-prueba/discovery/v2.0/keys",
    user_claim="oid",
    required_scope="access_as_user",
)
ISSUERS = [pytest.param(COGNITO, id="cognito"), pytest.param(ENTRA, id="entra")]


def _generate_private_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


SIGNING_KEY = _generate_private_key()
FOREIGN_KEY = _generate_private_key()


@dataclass(frozen=True)
class _SigningKey:
    key: RSAPublicKey


class _StaticKeys:
    """Stands in for the key provider: returns one public key, or raises a given error."""

    def __init__(self, public_key: RSAPublicKey, error: Exception | None = None) -> None:
        self._public_key = public_key
        self._error = error

    def get_signing_key_from_jwt(self, token: str) -> _SigningKey:
        if self._error is not None:
            raise self._error
        return _SigningKey(key=self._public_key)


def _claims(issuer: TokenIssuer) -> dict[str, object]:
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": issuer.issuer,
        "aud": issuer.audience,
        "iat": now,
        "exp": now + 3600,
        issuer.user_claim: "identificador-de-prueba",
        "email": "ops@example.com",
    }
    if issuer.kind == "cognito":
        claims.update({"token_use": "id", "email_verified": True})
    else:
        claims.update({"ver": "2.0", "scp": "openid access_as_user"})
    return claims


def _token(issuer: TokenIssuer, overrides: dict[str, object] | None = None, key: RSAPrivateKey = SIGNING_KEY) -> str:
    claims = _claims(issuer)
    claims.update(overrides or {})
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm="RS256", headers={"kid": "test-kid"})


def _verifier(issuer: TokenIssuer, keys: _StaticKeys | None = None) -> IssuerTokenVerifier:
    return IssuerTokenVerifier(issuer, keys or _StaticKeys(SIGNING_KEY.public_key()))


# --- Rules common to every issuer ---


@pytest.mark.parametrize("issuer", ISSUERS)
def test_a_valid_token_is_accepted_with_its_issuer_and_user_identifier(issuer: TokenIssuer) -> None:
    identity = _verifier(issuer).verify(_token(issuer))

    assert identity.issuer == issuer.issuer
    assert identity.subject == "identificador-de-prueba"
    assert identity.email == "ops@example.com"


@pytest.mark.parametrize("issuer", ISSUERS)
def test_a_token_signed_with_another_key_is_rejected(issuer: TokenIssuer) -> None:
    with pytest.raises(InvalidIdentityTokenError):
        _verifier(issuer).verify(_token(issuer, key=FOREIGN_KEY))


@pytest.mark.parametrize("issuer", ISSUERS)
def test_a_symmetric_algorithm_is_rejected(issuer: TokenIssuer) -> None:
    token = jwt.encode(_claims(issuer), "secreto-de-prueba-de-al-menos-32-bytes", algorithm="HS256")

    with pytest.raises(InvalidIdentityTokenError):
        _verifier(issuer).verify(token)


@pytest.mark.parametrize("issuer", ISSUERS)
def test_an_unsigned_token_is_rejected(issuer: TokenIssuer) -> None:
    token = jwt.encode(_claims(issuer), None, algorithm="none")

    with pytest.raises(InvalidIdentityTokenError):
        _verifier(issuer).verify(token)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"aud": "otra-audiencia"}, id="wrong-audience"),
        pytest.param({"iss": "https://emisor-de-prueba.example.com/otro"}, id="wrong-issuer"),
        pytest.param({"exp": int(time.time()) - 60}, id="expired"),
        pytest.param({"exp": None}, id="no-expiry"),
    ],
)
@pytest.mark.parametrize("issuer", ISSUERS)
def test_a_token_failing_a_common_claim_is_rejected(issuer: TokenIssuer, overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidIdentityTokenError):
        _verifier(issuer).verify(_token(issuer, overrides))


@pytest.mark.parametrize("issuer", ISSUERS)
def test_a_token_without_the_user_identifier_claim_is_rejected(issuer: TokenIssuer) -> None:
    with pytest.raises(InvalidIdentityTokenError):
        _verifier(issuer).verify(_token(issuer, {issuer.user_claim: None}))


@pytest.mark.parametrize("issuer", ISSUERS)
def test_a_malformed_token_is_rejected(issuer: TokenIssuer) -> None:
    with pytest.raises(InvalidIdentityTokenError):
        _verifier(issuer).verify("not-a-jwt")


@pytest.mark.parametrize("issuer", ISSUERS)
def test_unreachable_keys_are_reported_as_provider_unavailable(issuer: TokenIssuer) -> None:
    keys = _StaticKeys(SIGNING_KEY.public_key(), error=PyJWKClientConnectionError("connection refused"))

    with pytest.raises(IdentityProviderUnavailableError):
        _verifier(issuer, keys).verify(_token(issuer))


# --- Cognito rules ---


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"token_use": "access"}, id="access-token"),
        pytest.param({"email_verified": False}, id="unverified-email"),
        pytest.param({"email": None}, id="no-email"),
    ],
)
def test_a_cognito_token_failing_its_own_rules_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidIdentityTokenError):
        _verifier(COGNITO).verify(_token(COGNITO, overrides))


# --- Entra rules ---


def test_an_entra_token_without_the_scope_is_rejected() -> None:
    with pytest.raises(InvalidIdentityTokenError):
        _verifier(ENTRA).verify(_token(ENTRA, {"scp": "openid profile"}))


def test_an_entra_identity_token_is_rejected() -> None:
    # An identity token carries no scp claim.
    with pytest.raises(InvalidIdentityTokenError):
        _verifier(ENTRA).verify(_token(ENTRA, {"scp": None}))


def test_an_entra_version_1_token_is_rejected() -> None:
    with pytest.raises(InvalidIdentityTokenError):
        _verifier(ENTRA).verify(_token(ENTRA, {"ver": "1.0"}))


def test_an_entra_token_without_email_is_accepted_with_no_email() -> None:
    identity = _verifier(ENTRA).verify(_token(ENTRA, {"email": None}))

    assert identity.email is None
    assert identity.subject == "identificador-de-prueba"


def test_an_entra_roles_claim_is_ignored() -> None:
    identity = _verifier(ENTRA).verify(_token(ENTRA, {"roles": ["finance", "operations"]}))

    assert not hasattr(identity, "roles")
    assert identity.subject == "identificador-de-prueba"
