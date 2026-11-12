from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class RoleName(StrEnum):
    """Functional roles. Stored only in the database, never in Cognito."""

    OPERATIONS = "operations"
    BUSINESS = "business"
    FINANCE = "finance"
    TRADING = "trading"


@dataclass(frozen=True)
class VerifiedIdentity:
    """Who the identity provider says the caller is. Grants nothing by itself."""

    issuer: str
    subject: str
    # Entra may issue a token without an email claim.
    email: str | None


@dataclass(frozen=True)
class User:
    """Local user. Its roles decide what the caller may do."""

    id: int
    email: str
    full_name: str
    is_active: bool
    roles: frozenset[RoleName]
    # The (issuer, subject) link to the identity provider; None until the user's first access.
    identity_issuer: str | None = None
    identity_subject: str | None = None

    def has_any_role(self, accepted_roles: Iterable[RoleName]) -> bool:
        # Roles are additive: holding any one accepted role is enough.
        return not self.roles.isdisjoint(accepted_roles)
