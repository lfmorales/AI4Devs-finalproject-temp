"""The (issuer, subject) link columns of users: nullable, unique as a pair, and set together or not at all."""

from collections.abc import Iterator

import pytest
from sqlalchemy import String, exc, inspect
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.identity import UserRecord

ISSUER_A = "https://emisor-a.example.com/tenant-de-prueba/v2.0"
ISSUER_B = "https://emisor-b.example.com/pool-de-prueba"
EMAIL_PREFIX = "identity-link-"


@pytest.fixture
def session(test_db_session: Session) -> Iterator[Session]:
    yield test_db_session
    test_db_session.rollback()
    test_db_session.query(UserRecord).filter(UserRecord.email.like(f"{EMAIL_PREFIX}%")).delete(
        synchronize_session=False
    )
    test_db_session.commit()


def _user(number: int, issuer: str | None = None, subject: str | None = None) -> UserRecord:
    return UserRecord(
        email=f"{EMAIL_PREFIX}{number}@example.com",
        full_name="Test User",
        is_active=True,
        identity_issuer=issuer,
        identity_subject=subject,
    )


def test_both_columns_exist_are_nullable_and_255_long(session: Session) -> None:
    columns = {column["name"]: column for column in inspect(session.get_bind()).get_columns("users")}

    for name in ("identity_issuer", "identity_subject"):
        assert name in columns
        assert columns[name]["nullable"] is True
        column_type = columns[name]["type"]
        assert isinstance(column_type, String)
        assert column_type.length == 255
        assert columns[name]["default"] is None


def test_the_same_pair_cannot_belong_to_two_users(session: Session) -> None:
    session.add(_user(1, ISSUER_A, "sujeto-de-prueba"))
    session.commit()

    session.add(_user(2, ISSUER_A, "sujeto-de-prueba"))

    with pytest.raises(exc.IntegrityError):
        session.commit()


def test_several_users_may_have_no_link(session: Session) -> None:
    session.add_all([_user(3), _user(4), _user(5)])

    session.commit()

    assert session.query(UserRecord).filter(UserRecord.identity_issuer.is_(None)).count() >= 3


def test_the_same_subject_under_different_issuers_is_accepted(session: Session) -> None:
    session.add_all([_user(6, ISSUER_A, "mismo-sujeto"), _user(7, ISSUER_B, "mismo-sujeto")])

    session.commit()


@pytest.mark.parametrize(
    ("issuer", "subject"),
    [
        pytest.param(ISSUER_A, None, id="issuer-without-subject"),
        pytest.param(None, "sujeto-de-prueba", id="subject-without-issuer"),
    ],
)
def test_a_half_filled_link_is_rejected(session: Session, issuer: str | None, subject: str | None) -> None:
    session.add(_user(8, issuer, subject))

    with pytest.raises(exc.IntegrityError):
        session.commit()
