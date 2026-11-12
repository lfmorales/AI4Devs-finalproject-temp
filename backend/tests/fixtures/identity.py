"""In-memory doubles and builders for the identity model.

They let authentication and role enforcement be tested without Cognito
and without a database.
"""

from collections.abc import Iterable
from dataclasses import replace

from app.domain.exceptions import IdentityConflictError, InvalidIdentityTokenError
from app.domain.models.user import RoleName, User, VerifiedIdentity
from app.domain.repositories.user_repository import UserRepository
from app.domain.services.identity_token_verifier import IdentityTokenVerifier


def build_user(
    email: str = "ops@example.com",
    roles: Iterable[RoleName] = (RoleName.OPERATIONS,),
    is_active: bool = True,
    user_id: int = 1,
) -> User:
    return User(
        id=user_id,
        email=email,
        full_name="Example User",
        is_active=is_active,
        roles=frozenset(roles),
    )


class InMemoryUserRepository(UserRepository):
    def __init__(self, users: Iterable[User] = ()) -> None:
        self._users_by_email: dict[str, User] = {}
        for user in users:
            self.add(user)

    def add(self, user: User) -> None:
        self._users_by_email[user.email.lower()] = user

    def get_by_email(self, email: str) -> User | None:
        return self._users_by_email.get(email.lower())

    def get_by_identity(self, issuer: str, subject: str) -> User | None:
        for user in self._users_by_email.values():
            if (user.identity_issuer, user.identity_subject) == (issuer, subject):
                return user
        return None

    def set_active(self, user_id: int, active: bool, *, keep_one_active_with_role: RoleName | None = None) -> bool:
        user = self._find_by_id(user_id)
        if user is None:
            return False
        if not active and keep_one_active_with_role is not None:
            others = [
                other for other in self._users_by_email.values()
                if other.id != user_id and other.is_active and keep_one_active_with_role in other.roles
            ]
            if not others:
                return False
        self.add(replace(user, is_active=active))
        return True

    def count_active_with_role(self, role: RoleName) -> int:
        return sum(1 for user in self._users_by_email.values() if user.is_active and role in user.roles)

    def _find_by_id(self, user_id: int) -> User | None:
        return next((candidate for candidate in self._users_by_email.values() if candidate.id == user_id), None)

    def link_identity(self, user_id: int, issuer: str, subject: str) -> bool:
        user = self._find_by_id(user_id)
        if user is None or user.identity_issuer is not None:
            return False
        if self.get_by_identity(issuer, subject) is not None:
            raise IdentityConflictError("Identity already linked to another user")
        self.add(replace(user, identity_issuer=issuer, identity_subject=subject))
        return True


class FakeIdentityTokenVerifier(IdentityTokenVerifier):
    """Accepts only the tokens it was given, each mapped to an email."""

    def __init__(self, emails_by_token: dict[str, str]) -> None:
        self._emails_by_token = emails_by_token

    def verify(self, token: str) -> VerifiedIdentity:
        email = self._emails_by_token.get(token)
        if email is None:
            raise InvalidIdentityTokenError("Token is not valid")
        return VerifiedIdentity(issuer="https://emisor-de-prueba.example.com", subject=f"sub-{email}", email=email)
