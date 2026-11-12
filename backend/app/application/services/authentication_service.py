from collections.abc import Iterable

from app.domain.exceptions import InactiveUserError, MissingRoleError, UnregisteredUserError
from app.domain.models.user import RoleName, User
from app.domain.repositories.user_repository import UserRepository
from app.domain.services.identity_token_verifier import IdentityTokenVerifier


class AuthenticationService:
    """Resolves a bearer token to a local user and checks that user's roles."""

    def __init__(self, token_verifier: IdentityTokenVerifier, user_repository: UserRepository) -> None:
        self._token_verifier = token_verifier
        self._user_repository = user_repository

    def authenticate(self, token: str) -> User:
        identity = self._token_verifier.verify(token)
        # Provisional: the authentication task replaces this with the lookup by issuer and subject.
        if identity.email is None:
            raise UnregisteredUserError("Authenticated identity carries no email")
        user = self._user_repository.get_by_email(identity.email)
        if user is None:
            raise UnregisteredUserError("Authenticated user is not registered")
        if not user.is_active:
            raise InactiveUserError("Authenticated user is inactive")
        return user

    @staticmethod
    def authorize(user: User, accepted_roles: Iterable[RoleName]) -> None:
        required = frozenset(accepted_roles)
        # An empty requirement must never silently mean "open to everyone".
        if not required:
            raise ValueError("An operation must accept at least one role")
        if not user.has_any_role(required):
            raise MissingRoleError("User holds none of the accepted roles")
