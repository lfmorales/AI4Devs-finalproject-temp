from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.repositories.user_name_repository import UserNameRepository
from app.infrastructure.persistence.models.identity import UserRecord


class SqlAlchemyUserNameRepository(UserNameRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def names_and_emails(self, user_ids: Iterable[int]) -> dict[int, tuple[str, str]]:
        ids = list(user_ids)
        if not ids:
            return {}
        rows = self._session.execute(
            select(UserRecord.id, UserRecord.full_name, UserRecord.email).where(UserRecord.id.in_(ids))
        ).all()
        return {user_id: (name, email) for user_id, name, email in rows}
