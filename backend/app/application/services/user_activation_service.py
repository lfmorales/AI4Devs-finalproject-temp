from app.domain.exceptions import CannotDeactivateSelfError, LastActiveOperationsUserError, UserNotFoundError
from app.domain.models.user import RoleName, User
from app.domain.repositories.user_repository import UserRepository


class UserActivationService:
    """Lets an operations user set another user active or inactive, without locking operations out."""

    def __init__(self, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    def set_active(self, actor: User, email: str, active: bool) -> User:
        user = self._user_repository.get_by_email(email)
        if user is None:
            raise UserNotFoundError("No user has this email")
        if not active:
            if user.id == actor.id:
                raise CannotDeactivateSelfError("A user cannot deactivate their own account")
            # The last-operations-user rule is decided by the database in the transaction of the change.
            guarded_role = RoleName.OPERATIONS if RoleName.OPERATIONS in user.roles else None
            if user.is_active and not self._user_repository.set_active(
                user.id, False, keep_one_active_with_role=guarded_role
            ):
                raise LastActiveOperationsUserError("This is the last active operations user")
            return self._reload(email)
        self._user_repository.set_active(user.id, True)
        return self._reload(email)

    def _reload(self, email: str) -> User:
        user = self._user_repository.get_by_email(email)
        if user is None:
            raise UserNotFoundError("No user has this email")
        return user
