from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.domain.exceptions import IdentityConflictError
from app.domain.models.user import RoleName, User
from app.domain.repositories.user_repository import UserRepository
from app.infrastructure.persistence.models.identity import RoleRecord, UserRecord, UserRoleRecord

IDENTITY_PAIR_CONSTRAINT = "uq_users_identity_issuer_subject"


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_email(self, email: str) -> User | None:
        statement = (
            select(UserRecord)
            .where(func.lower(UserRecord.email) == email.lower())
            .options(selectinload(UserRecord.roles))
        )
        return self._to_user(self._session.scalars(statement).one_or_none())

    def get_by_identity(self, issuer: str, subject: str) -> User | None:
        statement = (
            select(UserRecord)
            .where(UserRecord.identity_issuer == issuer, UserRecord.identity_subject == subject)
            .options(selectinload(UserRecord.roles))
        )
        return self._to_user(self._session.scalars(statement).one_or_none())

    def link_identity(self, user_id: int, issuer: str, subject: str) -> bool:
        # Conditional on the user having no link, so two racing first accesses cannot overwrite each other.
        statement = (
            update(UserRecord)
            .where(UserRecord.id == user_id, UserRecord.identity_issuer.is_(None))
            .values(identity_issuer=issuer, identity_subject=subject)
        )
        try:
            stored = bool(self._session.execute(statement).rowcount == 1)  # type: ignore[attr-defined]
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            # The unique constraint is the last word when the pair belongs to another user.
            if getattr(error.orig.diag, "constraint_name", None) == IDENTITY_PAIR_CONSTRAINT:  # type: ignore[union-attr]
                raise IdentityConflictError("Identity already linked to another user") from None
            raise
        return stored

    def set_active(self, user_id: int, active: bool, *, keep_one_active_with_role: RoleName | None = None) -> bool:
        if not active and keep_one_active_with_role is not None:
            # Locks every active holder of the role, in id order, for the rest of this transaction. A simultaneous
            # deactivation waits here, and when it resumes it sees the state this one committed, so the last
            # holder cannot be removed twice over. (A plain EXISTS in the UPDATE would read the same old snapshot.)
            holders = self._session.scalars(
                select(UserRecord.id)
                .join(UserRoleRecord, UserRoleRecord.user_id == UserRecord.id)
                .join(RoleRecord, RoleRecord.id == UserRoleRecord.role_id)
                .where(RoleRecord.name == keep_one_active_with_role.value, UserRecord.is_active.is_(True))
                .order_by(UserRecord.id)
                .with_for_update(of=UserRecord)
            ).all()
            if not any(holder != user_id for holder in holders):
                self._session.rollback()
                return False
        result = self._session.execute(update(UserRecord).where(UserRecord.id == user_id).values(is_active=active))
        self._session.commit()
        return bool(result.rowcount == 1)  # type: ignore[attr-defined]

    def count_active_with_role(self, role: RoleName) -> int:
        return int(
            self._session.scalar(
                select(func.count(UserRecord.id))
                .join(UserRoleRecord, UserRoleRecord.user_id == UserRecord.id)
                .join(RoleRecord, RoleRecord.id == UserRoleRecord.role_id)
                .where(RoleRecord.name == role.value, UserRecord.is_active.is_(True))
            )
            or 0
        )

    @staticmethod
    def _to_user(record: UserRecord | None) -> User | None:
        if record is None:
            return None
        return User(
            id=record.id,
            email=record.email,
            full_name=record.full_name,
            is_active=record.is_active,
            roles=frozenset(RoleName(role.name) for role in record.roles),
            identity_issuer=record.identity_issuer,
            identity_subject=record.identity_subject,
        )
