"""In-memory doubles and builders for the identity model.

They let authentication and role enforcement be tested without Cognito
and without a database.
"""

from collections.abc import Iterable

from app.domain.exceptions import InvalidIdentityTokenError
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
        self._users_by_email: dict[str, User] = {user.email.lower(): user for user in users}

    def get_by_email(self, email: str) -> User | None:
        return self._users_by_email.get(email.lower())


class FakeIdentityTokenVerifier(IdentityTokenVerifier):
    """Accepts only the tokens it was given, each mapped to an email."""

    def __init__(self, emails_by_token: dict[str, str]) -> None:
        self._emails_by_token = emails_by_token

    def verify(self, token: str) -> VerifiedIdentity:
        email = self._emails_by_token.get(token)
        if email is None:
            raise InvalidIdentityTokenError("Token is not valid")
        return VerifiedIdentity(issuer="https://emisor-de-prueba.example.com", subject=f"sub-{email}", email=email)
