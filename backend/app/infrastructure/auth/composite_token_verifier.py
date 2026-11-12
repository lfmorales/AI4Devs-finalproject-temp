import jwt

from app.domain.exceptions import InvalidIdentityTokenError
from app.domain.models.user import VerifiedIdentity
from app.domain.services.identity_token_verifier import IdentityTokenVerifier

_MAX_TOKEN_LENGTH = 8192
# One message for every way the issuer cannot be chosen, so nothing of the token is echoed back.
_REJECTED_ISSUER_MESSAGE = "Token issuer is not accepted"


class CompositeTokenVerifier(IdentityTokenVerifier):
    """Chooses the verifier of the token's issuer and delegates to it, changing nothing of the result."""

    def __init__(self, verifiers_by_issuer: dict[str, IdentityTokenVerifier]) -> None:
        if not verifiers_by_issuer:
            raise ValueError("At least one issuer verifier is required")
        if not all(isinstance(issuer, str) for issuer in verifiers_by_issuer):
            raise ValueError("Every issuer must be text")
        self._verifiers_by_issuer = dict(verifiers_by_issuer)

    def verify(self, token: str) -> VerifiedIdentity:
        verifier = self._verifiers_by_issuer.get(self._unverified_issuer(token))
        if verifier is None:
            raise InvalidIdentityTokenError(_REJECTED_ISSUER_MESSAGE)
        return verifier.verify(token)

    @staticmethod
    def _unverified_issuer(token: str) -> str:
        """The `iss` claim, read WITHOUT checking the signature: it only chooses who verifies the token."""
        if not token or len(token) > _MAX_TOKEN_LENGTH:
            raise InvalidIdentityTokenError(_REJECTED_ISSUER_MESSAGE)
        try:
            claims = jwt.decode(token, options={"verify_signature": False})
        except (jwt.PyJWTError, ValueError):
            raise InvalidIdentityTokenError(_REJECTED_ISSUER_MESSAGE) from None
        issuer = claims.get("iss")
        if not isinstance(issuer, str):
            raise InvalidIdentityTokenError(_REJECTED_ISSUER_MESSAGE)
        return issuer
