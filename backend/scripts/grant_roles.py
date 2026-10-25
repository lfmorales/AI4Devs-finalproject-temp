"""Create the first user of a fresh deployment and give them roles, without any test data.

It creates the user if the email is unknown, creates only the requested role rows if they are missing, and
assigns the roles. It touches nothing else and reads nothing but DATABASE_URL. It prints counts only: never the
email, the roles or the text of an error.

Exit codes: 0 done; 1 the database failed; 2 invalid arguments; 3 DATABASE_URL is missing.

Run: python -m scripts.grant_roles <email> <role> [<role> ...]    (roles: operations, business, finance)
"""

import argparse
import os
import re
import sys
from collections.abc import Callable, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.persistence.database import build_engine, build_session_factory

EXIT_OK, EXIT_FAILED, EXIT_INVALID_ARGUMENTS, EXIT_NOT_CONFIGURED = 0, 1, 2, 3
ROLES = ("operations", "business", "finance")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class _InvalidArguments(Exception):
    """Carries no detail: the output never echoes what was typed."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # type: ignore[no-untyped-def]
        raise _InvalidArguments()


def main(
    argv: Sequence[str] | None = None,
    *,
    out: Callable[[str], None] = print,
    session_factory: Callable[[], Session] | None = None,
) -> int:
    try:
        email, roles = _parse(argv)
    except _InvalidArguments:
        out("status: invalid arguments")
        return EXIT_INVALID_ARGUMENTS

    engine = None
    if session_factory is None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            out("status: not configured")
            return EXIT_NOT_CONFIGURED
        engine = build_engine(database_url)
        session_factory = build_session_factory(engine)

    session = session_factory()
    try:
        users, created_roles, assigned = _grant(session, email, roles)
        session.commit()
    except Exception:
        session.rollback()
        out("status: failed")
        return EXIT_FAILED
    finally:
        session.close()
        if engine is not None:
            engine.dispose()

    out(f"user created: {users}")
    out(f"roles created: {created_roles}")
    out(f"roles assigned: {assigned}")
    return EXIT_OK


def _parse(argv: Sequence[str] | None) -> tuple[str, list[str]]:
    parser = _Parser(prog="grant_roles", description="Create a user and assign roles.")
    parser.add_argument("email")
    parser.add_argument("roles", nargs="+")
    arguments = parser.parse_args(argv)
    email = arguments.email.strip()
    if len(email) > 320 or not _EMAIL.match(email) or any(role not in ROLES for role in arguments.roles):
        raise _InvalidArguments()
    return email, list(dict.fromkeys(arguments.roles))


def _grant(session: Session, email: str, roles: list[str]) -> tuple[int, int, int]:
    created_roles = 0
    for role in roles:
        created_roles += session.execute(
            text("INSERT INTO roles (name) VALUES (:name) ON CONFLICT (name) DO NOTHING"), {"name": role}
        ).rowcount
    # full_name is mandatory and the command takes no name: the email stands in until someone edits it.
    created_users = session.execute(
        text("INSERT INTO users (email, full_name, is_active) VALUES (:email, :email, true) ON CONFLICT (email) DO NOTHING"),
        {"email": email},
    ).rowcount
    assigned = 0
    for role in roles:
        assigned += session.execute(
            text(
                "INSERT INTO user_roles (user_id, role_id)"
                " SELECT u.id, r.id FROM users u, roles r WHERE u.email = :email AND r.name = :role"
                " ON CONFLICT (user_id, role_id) DO NOTHING"
            ),
            {"email": email, "role": role},
        ).rowcount
    return created_users, created_roles, assigned


if __name__ == "__main__":
    sys.exit(main())
