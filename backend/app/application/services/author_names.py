from collections.abc import Iterable

from app.domain.repositories.user_name_repository import UserNameRepository
from app.domain.services.author_name import author_name


class AuthorNames:
    """Names the authors of billing events, for the responses of operations and finance. Writes nothing."""

    def __init__(self, users: UserNameRepository) -> None:
        self._users = users

    def of(self, user_ids: Iterable[int | None]) -> dict[int, str]:
        """The name of each author, or the email when the name is blank, by id; a missing user is not named."""
        stored = self._users.names_and_emails({user_id for user_id in user_ids if user_id is not None})
        return {user_id: author_name(name, email) for user_id, (name, email) in stored.items()}
