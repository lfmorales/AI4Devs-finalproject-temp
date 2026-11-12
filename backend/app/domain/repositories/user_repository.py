from abc import ABC, abstractmethod

from app.domain.models.user import RoleName, User


class UserRepository(ABC):
    @abstractmethod
    def get_by_email(self, email: str) -> User | None:
        """Return the user with this email, compared case-insensitively, with its roles."""

    @abstractmethod
    def get_by_identity(self, issuer: str, subject: str) -> User | None:
        """Return the user linked to this (issuer, subject) pair, matched exactly, with its roles."""

    @abstractmethod
    def link_identity(self, user_id: int, issuer: str, subject: str) -> bool:
        """Store the pair on a user that has no link yet.

        Returns True when stored, and False when the user already has a link (left unchanged) or does not exist.
        Raises IdentityConflictError when the pair already belongs to another user; nothing is changed.
        """

    @abstractmethod
    def set_active(self, user_id: int, active: bool, *, keep_one_active_with_role: RoleName | None = None) -> bool:
        """Set whether the user may use the system.

        With `keep_one_active_with_role`, a deactivation is refused when it would leave no other active user holding
        that role; the check and the change are one atomic step, so two simultaneous deactivations cannot both pass.
        Returns True when the state was set (also when it already was), and False when the guard refused or the
        user does not exist. A reactivation is never refused.
        """

    @abstractmethod
    def count_active_with_role(self, role: RoleName) -> int:
        """Return how many active users hold the role."""
