"""Identity tables: the minimum needed to resolve a user and their roles.

The migration that creates them belongs to the initial schema work
(register-campaign-from-purchase-order, group 1), not to the scaffolding.
"""

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.base import Base


class UserRecord(Base):
    __tablename__ = "users"
    __table_args__ = (
        # An (issuer, subject) pair identifies at most one user.
        UniqueConstraint("identity_issuer", "identity_subject", name="uq_users_identity_issuer_subject"),
        # A link is either complete or absent, never half filled.
        CheckConstraint(
            "(identity_issuer IS NULL) = (identity_subject IS NULL)", name="ck_users_identity_pair_complete"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Joined to the token's email claim only until the (issuer, subject) link below is stored.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # The stable link to the identity provider; empty until the user's first access.
    identity_issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    identity_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)

    roles: Mapped[list["RoleRecord"]] = relationship(secondary="user_roles", lazy="raise")


class RoleRecord(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)


class UserRoleRecord(Base):
    """Bridge table: a user may hold several roles. Never a role column on users."""

    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True)
