from abc import ABC, abstractmethod

from app.domain.models.user import VerifiedIdentity


class IdentityTokenVerifier(ABC):
    """Contract for verifying a bearer token. Implemented in infrastructure, one verifier per configured issuer."""

    @abstractmethod
    def verify(self, token: str) -> VerifiedIdentity:
        """Return the verified identity.

        Raises InvalidIdentityTokenError when the token cannot be trusted, and
        IdentityProviderUnavailableError when the provider's keys cannot be reached.
        """
