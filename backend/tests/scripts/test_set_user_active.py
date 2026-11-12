"""The active-state command: sets a user active or inactive by email, reports an unknown email, echoes nothing."""

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.identity import UserRecord
from scripts.set_user_active import (
    EXIT_FAILED,
    EXIT_INVALID_ARGUMENTS,
    EXIT_NOT_CONFIGURED,
    EXIT_OK,
    EXIT_USER_NOT_FOUND,
    main,
)

EMAIL = "someone.admin@example.org"


def _run(session: Session, *arguments: str) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = main(list(arguments), out=lines.append, session_factory=lambda: session)
    return code, lines


def _is_active(session: Session, email: str) -> bool:
    session.expire_all()
    return session.query(UserRecord).filter_by(email=email).one().is_active


@pytest.fixture
def user(rolled_back_session: Session) -> Session:
    rolled_back_session.add(UserRecord(email=EMAIL, full_name="Someone", is_active=True))
    rolled_back_session.commit()
    return rolled_back_session


def test_it_deactivates_and_then_reactivates_a_user(user: Session) -> None:
    code, _ = _run(user, "--email", EMAIL, "--inactive")
    assert code == EXIT_OK
    assert _is_active(user, EMAIL) is False

    code, _ = _run(user, "--email", EMAIL, "--active")
    assert code == EXIT_OK
    assert _is_active(user, EMAIL) is True


def test_it_matches_the_email_without_regard_to_case(user: Session) -> None:
    code, _ = _run(user, "--email", EMAIL.upper(), "--inactive")

    assert code == EXIT_OK
    assert _is_active(user, EMAIL) is False


def test_it_reports_an_unknown_email_changes_nothing_and_does_not_echo_it(user: Session) -> None:
    code, lines = _run(user, "--email", "nobody.here@example.org", "--inactive")

    assert code == EXIT_USER_NOT_FOUND
    assert any("not found" in line for line in lines)
    assert "nobody" not in "\n".join(lines)
    assert _is_active(user, EMAIL) is True


@pytest.mark.parametrize(
    "arguments",
    [
        ["--email", EMAIL],
        ["--email", EMAIL, "--active", "--inactive"],
        ["--active"],
        ["--email", "not-an-email", "--active"],
        [],
    ],
)
def test_invalid_arguments_exit_with_two_and_change_nothing(user: Session, arguments: list[str]) -> None:
    code, lines = _run(user, *arguments)

    assert code == EXIT_INVALID_ARGUMENTS
    assert "not-an-email" not in "\n".join(lines)
    assert _is_active(user, EMAIL) is True


def test_it_prints_no_email(user: Session) -> None:
    _, lines = _run(user, "--email", EMAIL, "--inactive")

    assert "example.org" not in "\n".join(lines)


def test_it_exits_with_three_when_the_database_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    lines: list[str] = []

    assert main(["--email", EMAIL, "--active"], out=lines.append) == EXIT_NOT_CONFIGURED


def test_a_database_failure_exits_with_one(user: Session) -> None:
    def broken_session() -> Session:
        raise RuntimeError("boom")

    lines: list[str] = []
    code = main(["--email", EMAIL, "--active"], out=lines.append, session_factory=broken_session)

    assert code == EXIT_FAILED
    assert "boom" not in "\n".join(lines)
