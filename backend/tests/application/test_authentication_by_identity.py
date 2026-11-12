"""Authentication joins the identity to a user by (issuer, subject), falling back to the email on the first access."""

import pytest

from app.application.services.authentication_service import AuthenticationService
from app.domain.exceptions import (
    IdentityConflictError,
    InactiveUserError,
    InvalidIdentityTokenError,
    UnregisteredUserError,
)
from app.domain.models.user import RoleName, User, VerifiedIdentity
from app.domain.services.identity_token_verifier import IdentityTokenVerifier
from tests.fixtures.identity import InMemoryUserRepository, build_user

ISSUER = "https://emisor-de-prueba.example.com"
OTHER_ISSUER = "https://otro-emisor-de-prueba.example.com"
SUBJECT = "sujeto-de-prueba"


class _FixedIdentityVerifier(IdentityTokenVerifier):
    def __init__(self, identity: VerifiedIdentity) -> None:
        self._identity = identity

    def verify(self, token: str) -> VerifiedIdentity:
        return self._identity


class _RejectingVerifier(IdentityTokenVerifier):
    def verify(self, token: str) -> VerifiedIdentity:
        raise InvalidIdentityTokenError("not valid")


class _RecordingRepository(InMemoryUserRepository):
    """Records every call so a test can tell which lookups and writes happened."""

    def __init__(self, users: list[User] | None = None) -> None:
        super().__init__(users or [])
        self.calls: list[str] = []

    def get_by_email(self, email: str) -> User | None:
        self.calls.append("get_by_email")
        return super().get_by_email(email)

    def get_by_identity(self, issuer: str, subject: str) -> User | None:
        self.calls.append("get_by_identity")
        return super().get_by_identity(issuer, subject)

    def link_identity(self, user_id: int, issuer: str, subject: str) -> bool:
        self.calls.append("link_identity")
        return super().link_identity(user_id, issuer, subject)


def _service(
    repository: InMemoryUserRepository, email: str | None = "ops@example.com", issuer: str = ISSUER
) -> AuthenticationService:
    identity = VerifiedIdentity(issuer=issuer, subject=SUBJECT, email=email)
    return AuthenticationService(token_verifier=_FixedIdentityVerifier(identity), user_repository=repository)


def _linked(user: User, issuer: str = ISSUER, subject: str = SUBJECT) -> User:
    from dataclasses import replace

    return replace(user, identity_issuer=issuer, identity_subject=subject)


def test_the_first_access_links_the_identity_and_lets_the_user_in() -> None:
    repository = _RecordingRepository([build_user(email="ops@example.com")])

    user = _service(repository).authenticate("token")

    assert user.email == "ops@example.com"
    stored = repository.get_by_identity(ISSUER, SUBJECT)
    assert stored is not None and stored.email == "ops@example.com"


def test_a_linked_user_is_found_by_the_pair_even_if_the_email_changed() -> None:
    repository = _RecordingRepository([_linked(build_user(email="antiguo@example.com"))])

    user = _service(repository, email="nuevo@example.com").authenticate("token")

    assert user.email == "antiguo@example.com"
    assert "link_identity" not in repository.calls
    assert "get_by_email" not in repository.calls


def test_an_email_of_a_user_linked_to_another_pair_is_a_conflict_and_the_link_does_not_change() -> None:
    repository = _RecordingRepository([_linked(build_user(email="ops@example.com"), OTHER_ISSUER, "otro-sujeto")])

    with pytest.raises(IdentityConflictError):
        _service(repository).authenticate("token")

    stored = repository.get_by_email("ops@example.com")
    assert stored is not None
    assert (stored.identity_issuer, stored.identity_subject) == (OTHER_ISSUER, "otro-sujeto")
    assert "link_identity" not in repository.calls


def test_an_identity_matching_no_user_is_not_registered_and_nothing_is_created() -> None:
    repository = _RecordingRepository([build_user(email="otro@example.com")])

    with pytest.raises(UnregisteredUserError):
        _service(repository, email="desconocido@example.com").authenticate("token")

    assert repository.get_by_email("desconocido@example.com") is None
    assert repository.get_by_identity(ISSUER, SUBJECT) is None
    assert "link_identity" not in repository.calls


def test_an_unlinked_identity_without_email_is_not_registered_and_nothing_is_stored() -> None:
    repository = _RecordingRepository([build_user(email="ops@example.com")])

    with pytest.raises(UnregisteredUserError):
        _service(repository, email=None).authenticate("token")

    assert "get_by_email" not in repository.calls
    assert "link_identity" not in repository.calls
    assert repository.get_by_identity(ISSUER, SUBJECT) is None


def test_an_inactive_user_found_by_the_pair_is_rejected() -> None:
    repository = _RecordingRepository([_linked(build_user(is_active=False))])

    with pytest.raises(InactiveUserError):
        _service(repository).authenticate("token")


def test_an_inactive_user_found_by_email_is_rejected_and_not_linked() -> None:
    repository = _RecordingRepository([build_user(email="ops@example.com", is_active=False)])

    with pytest.raises(InactiveUserError):
        _service(repository).authenticate("token")

    assert "link_identity" not in repository.calls
    assert repository.get_by_identity(ISSUER, SUBJECT) is None


class _SimultaneousAccessRepository(_RecordingRepository):
    """Another request links the same user first: link_identity reports False, yet the pair is that user's."""

    def link_identity(self, user_id: int, issuer: str, subject: str) -> bool:
        self.calls.append("link_identity")
        super().link_identity(user_id, issuer, subject)
        return False


def test_a_simultaneous_first_access_of_the_same_user_gets_in() -> None:
    repository = _SimultaneousAccessRepository([build_user(email="ops@example.com")])

    user = _service(repository).authenticate("token")

    assert user.email == "ops@example.com"


class _LostToAnotherUserRepository(_RecordingRepository):
    """link_identity reports False and the pair, when re-read, belongs to somebody else."""

    def link_identity(self, user_id: int, issuer: str, subject: str) -> bool:
        self.calls.append("link_identity")
        return False

    def get_by_identity(self, issuer: str, subject: str) -> User | None:
        self.calls.append("get_by_identity")
        if self.calls.count("get_by_identity") == 1:
            return None
        return build_user(email="otro@example.com", user_id=99)


def test_a_failed_link_whose_pair_belongs_to_another_user_is_a_conflict() -> None:
    repository = _LostToAnotherUserRepository([build_user(email="ops@example.com")])

    with pytest.raises(IdentityConflictError):
        _service(repository).authenticate("token")


class _ConflictOnLinkRepository(_RecordingRepository):
    def link_identity(self, user_id: int, issuer: str, subject: str) -> bool:
        raise IdentityConflictError("pair taken")


def test_a_conflict_raised_by_the_link_propagates() -> None:
    repository = _ConflictOnLinkRepository([build_user(email="ops@example.com")])

    with pytest.raises(IdentityConflictError):
        _service(repository).authenticate("token")


def test_an_invalid_token_is_rejected_without_querying_users() -> None:
    repository = _RecordingRepository([build_user()])
    service = AuthenticationService(token_verifier=_RejectingVerifier(), user_repository=repository)

    with pytest.raises(InvalidIdentityTokenError):
        service.authenticate("forged")

    assert repository.calls == []


def test_the_roles_are_the_ones_stored_for_the_user() -> None:
    repository = _RecordingRepository([build_user(email="ops@example.com", roles=[RoleName.BUSINESS])])

    user = _service(repository).authenticate("token")

    assert user.roles == frozenset({RoleName.BUSINESS})
