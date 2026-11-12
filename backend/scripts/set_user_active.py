"""Set a user active or inactive by email, for whoever administers the database.

It has none of the lock-out protections of the API endpoint: it can deactivate the last operations user, so run it
knowing that. It changes nothing but `users.is_active`, reads nothing but DATABASE_URL, and prints a status only:
never the email or the text of an error.

Exit codes: 0 done; 1 the database failed; 2 invalid arguments; 3 DATABASE_URL is missing; 4 no user has that email.

Run: python -m scripts.set_user_active --email <email> --active|--inactive
"""

import argparse
import os
import re
import sys
from collections.abc import Callable, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.persistence.database import build_engine, build_session_factory

EXIT_OK, EXIT_FAILED, EXIT_INVALID_ARGUMENTS, EXIT_NOT_CONFIGURED, EXIT_USER_NOT_FOUND = 0, 1, 2, 3, 4
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
        email, active = _parse(argv)
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

    try:
        session = session_factory()
    except Exception:
        out("status: failed")
        return EXIT_FAILED
    try:
        updated = int(
            session.execute(
                text("UPDATE users SET is_active = :active WHERE lower(email) = lower(:email)"),
                {"active": active, "email": email},
            ).rowcount  # type: ignore[attr-defined]
        )
        session.commit()
    except Exception:
        session.rollback()
        out("status: failed")
        return EXIT_FAILED
    finally:
        session.close()
        if engine is not None:
            engine.dispose()

    if updated == 0:
        out("status: user not found")
        return EXIT_USER_NOT_FOUND
    out(f"users updated: {updated}")
    out(f"state: {'active' if active else 'inactive'}")
    return EXIT_OK


def _parse(argv: Sequence[str] | None) -> tuple[str, bool]:
    parser = _Parser(prog="set_user_active", description="Set a user active or inactive.")
    parser.add_argument("--email", required=True)
    state = parser.add_mutually_exclusive_group(required=True)
    state.add_argument("--active", dest="active", action="store_true")
    state.add_argument("--inactive", dest="active", action="store_false")
    arguments = parser.parse_args(argv)
    email = arguments.email.strip()
    if len(email) > 320 or not _EMAIL.match(email):
        raise _InvalidArguments()
    return email, bool(arguments.active)


if __name__ == "__main__":
    sys.exit(main())
