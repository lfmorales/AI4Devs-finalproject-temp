from abc import ABC, abstractmethod
from collections.abc import Iterable


class UserNameRepository(ABC):
    @abstractmethod
    def names_and_emails(self, user_ids: Iterable[int]) -> dict[int, tuple[str, str]]:
        """The stored name and email of each of these users that exists, by id."""
