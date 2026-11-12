from collections.abc import Iterable
from dataclasses import replace

from app.domain.exceptions import (
    IdentityConflictError,
    InactiveUserError,
    MissingRoleError,
    UnregisteredUserError,
)
from app.domain.models.user import RoleName, User, VerifiedIdentity
from app.domain.repositories.user_repository import UserRepository
from app.domain.services.identity_token_verifier import IdentityTokenVerifier


class AuthenticationService:
    """Resolves a bearer token to a local user and checks that user's roles."""

    def __init__(self, token_verifier: IdentityTokenVerifier, user_repository: UserRepository) -> None:
        self._token_verifier = token_verifier
        self._user_repository = user_repository

    def authenticate(self, token: str) -> User:
        identity = self._token_verifier.verify(token)

        # The stable link wins, even when the email at the provider has changed since.
        user = self._user_repository.get_by_identity(identity.issuer, identity.subject)
        if user is None:
            user = self._find_unlinked_user_by_email(identity)
        if not user.is_active:
            # An inactive user is never linked.
            raise InactiveUserError("Authenticated user is inactive")
        if user.identity_issuer is None:
            user = self._link(user, identity)
        # Roles are those stored for the user; nothing in the token decides them.
        return user

    def _find_unlinked_user_by_email(self, identity: VerifiedIdentity) -> User:
        """First access: the email only locates a registered user that has no link yet. Never creates a user."""
        if identity.email is None:
            raise UnregisteredUserError("Authenticated identity carries no email")
        user = self._user_repository.get_by_email(identity.email)
        if user is None:
            raise UnregisteredUserError("Authenticated user is not registered")
        if user.identity_issuer is not None:
            raise IdentityConflictError("User is already linked to a different identity")
        return user

    def _link(self, user: User, identity: VerifiedIdentity) -> User:
        if self._user_repository.link_identity(user.id, identity.issuer, identity.subject):
            return replace(user, identity_issuer=identity.issuer, identity_subject=identity.subject)
        # Not stored: either a simultaneous first access of this same user got there first, or the pair is not theirs.
        linked_user = self._user_repository.get_by_identity(identity.issuer, identity.subject)
        if linked_user is None or linked_user.id != user.id:
            raise IdentityConflictError("Identity could not be linked to this user")
        return linked_user

    @staticmethod
    def authorize(user: User, accepted_roles: Iterable[RoleName]) -> None:
        required = frozenset(accepted_roles)
        # An empty requirement must never silently mean "open to everyone".
        if not required:
            raise ValueError("An operation must accept at least one role")
        if not user.has_any_role(required):
            raise MissingRoleError("User holds none of the accepted roles")
