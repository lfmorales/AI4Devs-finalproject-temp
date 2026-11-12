from collections.abc import Callable
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWKClientError

from app.config import TokenIssuer
from app.domain.exceptions import IdentityProviderUnavailableError, InvalidIdentityTokenError
from app.domain.models.user import VerifiedIdentity
from app.domain.services.identity_token_verifier import IdentityTokenVerifier

# Only an asymmetric algorithm: never "none" and never a shared-secret one.
_ALGORITHMS = ["RS256"]
_COMMON_REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud"]


class SigningKeyProvider(Protocol):
    """The subset of PyJWKClient this verifier uses, so tests can supply their own keys."""

    def get_signing_key_from_jwt(self, token: str) -> Any: ...


def _cognito_email(claims: dict[str, Any], issuer: TokenIssuer) -> str | None:
    """Cognito: an ID token with a verified email, because only the ID token carries the email."""
    if claims.get("token_use") != "id":
        raise InvalidIdentityTokenError("Token is not an ID token")
    email = claims.get("email")
    if not isinstance(email, str) or not email:
        raise InvalidIdentityTokenError("Token carries no email claim")
    # An unverified email must not be trusted as the join key to a local user.
    if claims.get("email_verified") is not True:
        raise InvalidIdentityTokenError("Token email is not verified")
    return email


def _entra_email(claims: dict[str, Any], issuer: TokenIssuer) -> str | None:
    """Entra: a version 2 access token with the mandatory scope. The email may be absent; `roles` is ignored."""
    if claims.get("ver") != "2.0":
        raise InvalidIdentityTokenError("Token is not a version 2 token")
    if issuer.required_scope is not None:
        scope = claims.get("scp")
        # An identity token carries no scp claim, so it is rejected here.
        if not isinstance(scope, str) or issuer.required_scope not in scope.split():
            raise InvalidIdentityTokenError("Token lacks the required scope")
    email = claims.get("email")
    return email if isinstance(email, str) and email else None


# What each kind of issuer adds to the common rules, and where it takes the email from.
_RULES_BY_KIND: dict[str, Callable[[dict[str, Any], TokenIssuer], str | None]] = {
    "cognito": _cognito_email,
    "entra": _entra_email,
}


class IssuerTokenVerifier(IdentityTokenVerifier):
    """Verifies the bearer tokens of ONE configured issuer against that issuer's keys."""

    def __init__(self, issuer: TokenIssuer, jwks_client: SigningKeyProvider | None = None) -> None:
        self._issuer = issuer
        # PyJWKClient caches the key set and refetches it when an unknown kid appears.
        self._jwks_client = jwks_client or PyJWKClient(issuer.jwks_url)

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
        except PyJWKClientConnectionError as error:
            raise IdentityProviderUnavailableError("Identity provider keys are unreachable") from error
        except (PyJWKClientError, jwt.PyJWTError) as error:
            raise InvalidIdentityTokenError("Token signing key could not be resolved") from error

        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=_ALGORITHMS,
                audience=self._issuer.audience,
                issuer=self._issuer.issuer,
                options={"require": [*_COMMON_REQUIRED_CLAIMS, self._issuer.user_claim]},
            )
        except jwt.PyJWTError as error:
            raise InvalidIdentityTokenError("Token failed verification") from error

        email = _RULES_BY_KIND[self._issuer.kind](claims, self._issuer)
        return VerifiedIdentity(
            issuer=self._issuer.issuer, subject=str(claims[self._issuer.user_claim]), email=email
        )
