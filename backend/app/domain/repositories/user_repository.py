from abc import ABC, abstractmethod

from app.domain.models.user import User


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
