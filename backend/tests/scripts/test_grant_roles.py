"""The first-user command: creates the user and the requested roles, is idempotent, and echoes nothing it was given."""

import pytest
from sqlalchemy import func, select

from app.infrastructure.persistence.models.identity import RoleRecord, UserRecord, UserRoleRecord
from scripts.grant_roles import EXIT_FAILED, EXIT_INVALID_ARGUMENTS, EXIT_NOT_CONFIGURED, EXIT_OK, main

EMAIL = "first.operator@example.org"


def _run(session, *arguments: str) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = main(list(arguments), out=lines.append, session_factory=lambda: session)
    return code, lines


def _roles_of(session, email: str) -> set[str]:
    rows = session.scalars(
        select(RoleRecord.name)
        .join(UserRoleRecord, UserRoleRecord.role_id == RoleRecord.id)
        .join(UserRecord, UserRecord.id == UserRoleRecord.user_id)
        .where(UserRecord.email == email)
    )
    return set(rows)


def _count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_it_creates_the_user_and_the_requested_roles(rolled_back_session):
    code, _ = _run(rolled_back_session, EMAIL, "operations")

    assert code == EXIT_OK
    assert _roles_of(rolled_back_session, EMAIL) == {"operations"}
    user = rolled_back_session.scalar(select(UserRecord).where(UserRecord.email == EMAIL))
    assert user.is_active is True


def test_it_assigns_several_roles_at_once(rolled_back_session):
    code, _ = _run(rolled_back_session, EMAIL, "operations", "finance")

    assert code == EXIT_OK
    assert _roles_of(rolled_back_session, EMAIL) == {"operations", "finance"}


def test_it_creates_only_the_requested_role_rows(rolled_back_session):
    before = set(rolled_back_session.scalars(select(RoleRecord.name)))

    _run(rolled_back_session, EMAIL, "business")

    assert set(rolled_back_session.scalars(select(RoleRecord.name))) == before | {"business"}


def test_running_it_twice_changes_nothing_the_second_time(rolled_back_session):
    _run(rolled_back_session, EMAIL, "operations")
    users, roles, links = (_count(rolled_back_session, m) for m in (UserRecord, RoleRecord, UserRoleRecord))

    code, _ = _run(rolled_back_session, EMAIL, "operations")

    assert code == EXIT_OK
    assert (_count(rolled_back_session, UserRecord), _count(rolled_back_session, RoleRecord),
            _count(rolled_back_session, UserRoleRecord)) == (users, roles, links)


def test_it_adds_a_role_to_an_existing_user_and_keeps_the_others(rolled_back_session):
    _run(rolled_back_session, EMAIL, "operations")

    _run(rolled_back_session, EMAIL, "business")

    assert _roles_of(rolled_back_session, EMAIL) == {"operations", "business"}


@pytest.mark.parametrize("arguments", [
    ["not-an-email", "operations"],
    ["", "operations"],
    [EMAIL, "superuser"],
    [EMAIL],
    [],
])
def test_invalid_arguments_exit_with_two_and_write_nothing(rolled_back_session, arguments):
    users = _count(rolled_back_session, UserRecord)

    code, _ = _run(rolled_back_session, *arguments)

    assert code == EXIT_INVALID_ARGUMENTS
    assert _count(rolled_back_session, UserRecord) == users


def test_it_prints_counts_and_never_the_email_or_the_roles_given(rolled_back_session):
    _, lines = _run(rolled_back_session, EMAIL, "operations", "finance")
    _, invalid_lines = _run(rolled_back_session, "typo@@example.org", "operations")

    output = "\n".join(lines + invalid_lines)
    assert "first.operator" not in output
    assert "example.org" not in output
    assert "finance" not in output
    assert "user created: 1" in output


def test_without_a_database_url_it_reports_not_configured_and_prints_nothing_else(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    lines: list[str] = []

    code = main([EMAIL, "operations"], out=lines.append)

    assert code == EXIT_NOT_CONFIGURED
    assert lines == ["status: not configured"]


def test_a_database_failure_exits_with_one_and_leaks_no_detail(rolled_back_session):
    class Broken:
        def execute(self, *args, **kwargs):
            raise RuntimeError(f"password authentication failed for {EMAIL}")

        def rollback(self):
            pass

        def close(self):
            pass

    lines: list[str] = []

    code = main([EMAIL, "operations"], out=lines.append, session_factory=lambda: Broken())

    assert code == EXIT_FAILED
    assert EMAIL not in "\n".join(lines)
    assert "password" not in "\n".join(lines)
