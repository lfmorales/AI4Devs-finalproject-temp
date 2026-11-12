"""One contract for finding and linking users by (issuer, subject), run against the in-memory and the SQL repository."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

import pytest
from sqlalchemy.orm import Session

from app.domain.exceptions import IdentityConflictError
from app.domain.models.user import RoleName
from app.domain.repositories.user_repository import UserRepository
from app.infrastructure.persistence.models.identity import RoleRecord, UserRecord, UserRoleRecord
from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from tests.fixtures.identity import InMemoryUserRepository, build_user

ISSUER = "https://emisor-de-prueba.example.com/v2.0"
OTHER_ISSUER = "https://otro-emisor-de-prueba.example.com"
SUBJECT = "Sujeto-De-Prueba"

AddUser = Callable[..., int]


@dataclass
class Harness:
    repository: UserRepository
    add_user: AddUser


def _memory_harness() -> Harness:
    repository = InMemoryUserRepository()
    next_id = iter(range(1, 1000))

    def add_user(
        email: str,
        roles: Iterable[RoleName] = (RoleName.OPERATIONS,),
        issuer: str | None = None,
        subject: str | None = None,
    ) -> int:
        user = build_user(email=email, roles=roles, user_id=next(next_id))
        repository.add(replace(user, identity_issuer=issuer, identity_subject=subject))
        return user.id

    return Harness(repository, add_user)


def _sql_harness(session: Session) -> Harness:
    def add_user(
        email: str,
        roles: Iterable[RoleName] = (RoleName.OPERATIONS,),
        issuer: str | None = None,
        subject: str | None = None,
    ) -> int:
        record = UserRecord(
            email=email, full_name="Example User", is_active=True, identity_issuer=issuer, identity_subject=subject
        )
        session.add(record)
        session.flush()
        for role in roles:
            role_record = session.query(RoleRecord).filter_by(name=role.value).one_or_none()
            if role_record is None:
                role_record = RoleRecord(name=role.value)
                session.add(role_record)
                session.flush()
            session.add(UserRoleRecord(user_id=record.id, role_id=role_record.id))
        # Committed, as in production: a rollback inside the repository must not undo the seeded users.
        session.commit()
        return record.id

    return Harness(SqlAlchemyUserRepository(session), add_user)


@pytest.fixture(params=["in-memory", "sqlalchemy"])
def harness(request: pytest.FixtureRequest, rolled_back_session: Session) -> Harness:
    return _memory_harness() if request.param == "in-memory" else _sql_harness(rolled_back_session)


def test_get_by_identity_finds_the_user_with_its_roles(harness: Harness) -> None:
    user_id = harness.add_user(
        "ops@example.com", roles=[RoleName.OPERATIONS, RoleName.FINANCE], issuer=ISSUER, subject=SUBJECT
    )

    user = harness.repository.get_by_identity(ISSUER, SUBJECT)

    assert user is not None
    assert user.id == user_id
    assert user.roles == frozenset({RoleName.OPERATIONS, RoleName.FINANCE})
    assert (user.identity_issuer, user.identity_subject) == (ISSUER, SUBJECT)


def test_get_by_identity_returns_none_for_a_pair_nobody_has(harness: Harness) -> None:
    harness.add_user("ops@example.com", issuer=ISSUER, subject=SUBJECT)

    assert harness.repository.get_by_identity(ISSUER, "otro-sujeto") is None


@pytest.mark.parametrize(
    ("issuer", "subject"),
    [
        pytest.param(ISSUER, SUBJECT.upper(), id="subject-in-other-case"),
        pytest.param(ISSUER.upper(), SUBJECT, id="issuer-in-other-case"),
        pytest.param(OTHER_ISSUER, SUBJECT, id="other-issuer"),
    ],
)
def test_get_by_identity_matches_the_pair_exactly(harness: Harness, issuer: str, subject: str) -> None:
    harness.add_user("ops@example.com", issuer=ISSUER, subject=SUBJECT)

    assert harness.repository.get_by_identity(issuer, subject) is None


def test_link_identity_stores_the_pair_of_a_user_without_link(harness: Harness) -> None:
    user_id = harness.add_user("ops@example.com")

    assert harness.repository.link_identity(user_id, ISSUER, SUBJECT) is True

    user = harness.repository.get_by_email("ops@example.com")
    assert user is not None
    assert (user.identity_issuer, user.identity_subject) == (ISSUER, SUBJECT)


def test_after_linking_the_user_is_found_by_identity_and_by_email(harness: Harness) -> None:
    user_id = harness.add_user("ops@example.com", roles=[RoleName.FINANCE])
    harness.repository.link_identity(user_id, ISSUER, SUBJECT)

    by_identity = harness.repository.get_by_identity(ISSUER, SUBJECT)
    by_email = harness.repository.get_by_email("OPS@example.com")

    assert by_identity is not None and by_email is not None
    assert by_identity.id == by_email.id == user_id
    assert by_identity.roles == frozenset({RoleName.FINANCE})


def test_link_identity_leaves_a_user_that_already_has_a_link_unchanged(harness: Harness) -> None:
    user_id = harness.add_user("ops@example.com", issuer=ISSUER, subject=SUBJECT)

    assert harness.repository.link_identity(user_id, OTHER_ISSUER, "sujeto-nuevo") is False

    user = harness.repository.get_by_email("ops@example.com")
    assert user is not None
    assert (user.identity_issuer, user.identity_subject) == (ISSUER, SUBJECT)
    assert harness.repository.get_by_identity(OTHER_ISSUER, "sujeto-nuevo") is None


def test_link_identity_returns_false_for_an_id_that_does_not_exist(harness: Harness) -> None:
    harness.add_user("ops@example.com")

    assert harness.repository.link_identity(99999, ISSUER, SUBJECT) is False
    assert harness.repository.get_by_identity(ISSUER, SUBJECT) is None


def test_link_identity_with_a_pair_of_another_user_raises_and_changes_nothing(harness: Harness) -> None:
    harness.add_user("first@example.com", issuer=ISSUER, subject=SUBJECT)
    second_id = harness.add_user("second@example.com")

    with pytest.raises(IdentityConflictError):
        harness.repository.link_identity(second_id, ISSUER, SUBJECT)

    second = harness.repository.get_by_email("second@example.com")
    first = harness.repository.get_by_identity(ISSUER, SUBJECT)
    assert second is not None and first is not None
    assert (second.identity_issuer, second.identity_subject) == (None, None)
    assert first.email == "first@example.com"


def test_the_repository_stays_usable_after_a_conflict(harness: Harness) -> None:
    harness.add_user("first@example.com", issuer=ISSUER, subject=SUBJECT)
    second_id = harness.add_user("second@example.com")
    with pytest.raises(IdentityConflictError):
        harness.repository.link_identity(second_id, ISSUER, SUBJECT)

    assert harness.repository.link_identity(second_id, ISSUER, "sujeto-libre") is True
    assert harness.repository.get_by_identity(ISSUER, "sujeto-libre") is not None
