"""The composite picks the verifier by the unverified `iss`, matched exactly, and delegates everything else."""

import base64
import json
import time
from dataclasses import dataclass

import jwt
import pytest
from jwt.api_jws import PyJWS
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from app.config import TokenIssuer
from app.domain.exceptions import IdentityProviderUnavailableError, InvalidIdentityTokenError
from app.domain.models.user import VerifiedIdentity
from app.domain.services.identity_token_verifier import IdentityTokenVerifier
from app.infrastructure.auth.composite_token_verifier import CompositeTokenVerifier
from app.infrastructure.auth.issuer_token_verifier import IssuerTokenVerifier

ISSUER_A = "https://emisor-a.example.com/tenant-de-prueba/v2.0"
ISSUER_B = "https://emisor-b.example.com/pool-de-prueba"


class _RecordingVerifier(IdentityTokenVerifier):
    def __init__(self, identity: VerifiedIdentity | None = None, error: Exception | None = None) -> None:
        self.received: list[str] = []
        self._identity = identity
        self._error = error

    def verify(self, token: str) -> VerifiedIdentity:
        self.received.append(token)
        if self._error is not None:
            raise self._error
        assert self._identity is not None
        return self._identity


def _unsigned_token(claims: dict[str, object]) -> str:
    return jwt.encode(claims, key="", algorithm="none")


def _hs256_token(claims: dict[str, object]) -> str:
    # Signs the raw JSON so claims of the wrong type, such as a numeric iss, can be built.
    payload = json.dumps(claims).encode()
    return PyJWS().encode(payload, "secreto-de-prueba-de-al-menos-32-bytes", algorithm="HS256")


def _identity(issuer: str, subject: str) -> VerifiedIdentity:
    return VerifiedIdentity(issuer=issuer, subject=subject, email="ops@example.com")


@pytest.fixture
def verifier_a() -> _RecordingVerifier:
    return _RecordingVerifier(_identity(ISSUER_A, "sujeto-a"))


@pytest.fixture
def verifier_b() -> _RecordingVerifier:
    return _RecordingVerifier(_identity(ISSUER_B, "sujeto-b"))


@pytest.fixture
def composite(verifier_a: _RecordingVerifier, verifier_b: _RecordingVerifier) -> CompositeTokenVerifier:
    return CompositeTokenVerifier({ISSUER_A: verifier_a, ISSUER_B: verifier_b})


def test_each_token_goes_to_its_own_verifier_exactly_once(
    composite: CompositeTokenVerifier, verifier_a: _RecordingVerifier, verifier_b: _RecordingVerifier
) -> None:
    token_a = _hs256_token({"iss": ISSUER_A})
    token_b = _hs256_token({"iss": ISSUER_B})

    composite.verify(token_a)
    assert (verifier_a.received, verifier_b.received) == ([token_a], [])

    composite.verify(token_b)
    assert (verifier_a.received, verifier_b.received) == ([token_a], [token_b])


def test_the_identity_returned_is_the_one_of_the_chosen_verifier(
    composite: CompositeTokenVerifier, verifier_b: _RecordingVerifier
) -> None:
    assert composite.verify(_hs256_token({"iss": ISSUER_B})) is verifier_b._identity


def test_the_provider_unavailable_error_propagates_unchanged() -> None:
    error = IdentityProviderUnavailableError("keys unreachable")
    composite = CompositeTokenVerifier({ISSUER_A: _RecordingVerifier(error=error)})

    with pytest.raises(IdentityProviderUnavailableError) as raised:
        composite.verify(_hs256_token({"iss": ISSUER_A}))

    assert raised.value is error


def test_an_invalid_token_error_of_the_chosen_verifier_propagates_unchanged() -> None:
    error = InvalidIdentityTokenError("chosen verifier said no")
    composite = CompositeTokenVerifier({ISSUER_A: _RecordingVerifier(error=error)})

    with pytest.raises(InvalidIdentityTokenError) as raised:
        composite.verify(_hs256_token({"iss": ISSUER_A}))

    assert raised.value is error


@pytest.mark.parametrize(
    "claims",
    [
        pytest.param({"iss": "https://desconocido.example.com"}, id="unknown-issuer"),
        pytest.param({"iss": ISSUER_A + "/"}, id="different-trailing-slash"),
        pytest.param({"iss": ISSUER_A.upper()}, id="different-case"),
        pytest.param({"iss": ISSUER_A.replace("/v2.0", "")}, id="prefix-of-a-valid-issuer"),
        pytest.param({"iss": ISSUER_A + "/extra"}, id="valid-issuer-as-a-prefix"),
        pytest.param({"sub": "sin-emisor"}, id="no-iss"),
        pytest.param({"iss": 12345}, id="numeric-iss"),
        pytest.param({"iss": [ISSUER_A]}, id="list-iss"),
        pytest.param({"iss": None}, id="null-iss"),
    ],
)
def test_an_issuer_that_is_not_exactly_a_configured_one_is_rejected_without_reaching_any_verifier(
    composite: CompositeTokenVerifier,
    verifier_a: _RecordingVerifier,
    verifier_b: _RecordingVerifier,
    claims: dict[str, object],
) -> None:
    with pytest.raises(InvalidIdentityTokenError) as raised:
        composite.verify(_hs256_token(claims))

    assert (verifier_a.received, verifier_b.received) == ([], [])
    assert str(raised.value) == "Token issuer is not accepted"


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("", id="empty"),
        pytest.param("esto-no-es-un-jwt", id="not-a-jwt"),
        pytest.param("a.b.c", id="three-segments-not-base64-json"),
        pytest.param("x" * 8193, id="longer-than-8192"),
        pytest.param("e30.e30.é", id="non-ascii-segment"),
    ],
)
def test_a_malformed_or_oversized_token_is_rejected_with_a_fixed_message(
    composite: CompositeTokenVerifier, verifier_a: _RecordingVerifier, token: str
) -> None:
    with pytest.raises(InvalidIdentityTokenError) as raised:
        composite.verify(token)

    assert verifier_a.received == []
    assert str(raised.value) == "Token issuer is not accepted"


def test_a_payload_that_is_not_a_json_object_is_rejected() -> None:
    composite = CompositeTokenVerifier({ISSUER_A: _RecordingVerifier()})
    segment = base64.urlsafe_b64encode(json.dumps(["no", "objeto"]).encode()).rstrip(b"=").decode()
    token = f"e30.{segment}.firma"

    with pytest.raises(InvalidIdentityTokenError):
        composite.verify(token)


def test_a_token_of_exactly_8192_characters_is_still_read() -> None:
    verifier = _RecordingVerifier(_identity(ISSUER_A, "sujeto-a"))
    composite = CompositeTokenVerifier({ISSUER_A: verifier})
    head = _hs256_token({"iss": ISSUER_A}).rsplit(".", 1)[0]
    token = head + "." + "A" * (8192 - len(head) - 1)
    assert len(token) == 8192

    composite.verify(token)

    assert verifier.received == [token]


def test_building_with_no_verifiers_is_refused() -> None:
    with pytest.raises(ValueError):
        CompositeTokenVerifier({})


@pytest.mark.parametrize("key", [1, None, b"https://emisor.example.com", ("a",)])
def test_building_with_a_key_that_is_not_text_is_refused(key: object) -> None:
    with pytest.raises(ValueError):
        CompositeTokenVerifier({key: _RecordingVerifier()})  # type: ignore[dict-item]


# --- With two real per-issuer verifiers ---

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


@dataclass(frozen=True)
class _SigningKey:
    key: RSAPublicKey


class _StaticKeys:
    def __init__(self, public_key: RSAPublicKey) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token: str) -> _SigningKey:
        return _SigningKey(key=self._public_key)


def _generate_private_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


COGNITO_KEY = _generate_private_key()
ENTRA_KEY = _generate_private_key()


def _issuer_token(issuer: TokenIssuer, key: RSAPrivateKey, overrides: dict[str, object] | None = None) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": issuer.issuer,
        "aud": issuer.audience,
        "iat": now,
        "exp": now + 3600,
        issuer.user_claim: f"sujeto-{issuer.kind}",
        "email": "ops@example.com",
    }
    if issuer.kind == "cognito":
        claims.update({"token_use": "id", "email_verified": True})
    else:
        claims.update({"ver": "2.0", "scp": "access_as_user"})
    claims.update(overrides or {})
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-kid"})


@pytest.fixture
def real_composite() -> CompositeTokenVerifier:
    return CompositeTokenVerifier(
        {
            COGNITO.issuer: IssuerTokenVerifier(COGNITO, _StaticKeys(COGNITO_KEY.public_key())),
            ENTRA.issuer: IssuerTokenVerifier(ENTRA, _StaticKeys(ENTRA_KEY.public_key())),
        }
    )


def test_each_real_verifier_accepts_only_the_tokens_of_its_own_issuer(real_composite: CompositeTokenVerifier) -> None:
    cognito_identity = real_composite.verify(_issuer_token(COGNITO, COGNITO_KEY))
    entra_identity = real_composite.verify(_issuer_token(ENTRA, ENTRA_KEY))

    assert (cognito_identity.issuer, cognito_identity.subject) == (COGNITO.issuer, "sujeto-cognito")
    assert (entra_identity.issuer, entra_identity.subject) == (ENTRA.issuer, "sujeto-entra")


def test_a_token_signed_by_the_other_issuers_key_is_rejected(real_composite: CompositeTokenVerifier) -> None:
    with pytest.raises(InvalidIdentityTokenError):
        real_composite.verify(_issuer_token(ENTRA, COGNITO_KEY))
    with pytest.raises(InvalidIdentityTokenError):
        real_composite.verify(_issuer_token(COGNITO, ENTRA_KEY))


def test_a_token_for_another_audience_is_rejected(real_composite: CompositeTokenVerifier) -> None:
    with pytest.raises(InvalidIdentityTokenError):
        real_composite.verify(_issuer_token(ENTRA, ENTRA_KEY, {"aud": COGNITO.audience}))


def test_an_unsigned_token_with_a_valid_issuer_is_rejected_by_that_issuers_verifier(
    real_composite: CompositeTokenVerifier,
) -> None:
    token = _unsigned_token({"iss": ENTRA.issuer, "aud": ENTRA.audience, "oid": "x"})

    with pytest.raises(InvalidIdentityTokenError):
        real_composite.verify(token)
