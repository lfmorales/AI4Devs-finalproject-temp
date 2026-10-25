"""Load the master data of a fresh deployment from a JSON file.

Each item is identified by its name and created if it does not exist; nothing existing is modified or deleted.
Everything happens in one transaction. It prints counts per table only: never a name or any other content of the
file.

Exit codes: 0 done; 1 the database failed; 2 invalid file or arguments; 3 DATABASE_URL is missing.

Run: python -m scripts.load_masters FILE.json
"""

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.persistence.database import build_engine, build_session_factory

EXIT_OK, EXIT_FAILED, EXIT_INVALID, EXIT_NOT_CONFIGURED = 0, 1, 2, 3

# Sections in loading order: agencies need their groups first.
SECTIONS = (
    "holding_groups", "agencies", "advertisers", "dsps", "channels", "formats", "campaign_types", "sectors",
    "sales_reps",
)


def main(
    argv: Sequence[str] | None = None,
    *,
    out: Callable[[str], None] = print,
    session_factory: Callable[[], Session] | None = None,
) -> int:
    arguments = _parse(argv)
    with open(arguments.file, encoding="utf-8") as handle:
        content: dict[str, list[dict[str, Any]]] = json.load(handle)

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
        created = {section: _load(session, section, content.get(section, [])) for section in SECTIONS}
        session.commit()
    except Exception:
        session.rollback()
        out("status: failed")
        return EXIT_FAILED
    finally:
        session.close()
        if engine is not None:
            engine.dispose()

    for section in SECTIONS:
        total = len(content.get(section, []))
        out(f"{section}: created {created[section]}, existing {total - created[section]}")
    return EXIT_OK


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="load_masters", description="Load the master data from a JSON file.")
    parser.add_argument("file")
    return parser.parse_args(argv)


def _load(session: Session, section: str, items: list[dict[str, Any]]) -> int:
    created = 0
    for item in items:
        created += session.execute(*_insert(section, item)).rowcount
    return created


def _insert(section: str, item: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    name = item["name"].strip()
    if section == "agencies":
        return (
            text(
                "INSERT INTO agencies (holding_group_id, name)"
                " SELECT id, :name FROM holding_groups WHERE name = :group ON CONFLICT (name) DO NOTHING"
            ),
            {"name": name, "group": item["holding_group"].strip()},
        )
    if section == "dsps":
        return (
            text(
                "INSERT INTO dsps (name, is_active) VALUES (:name, COALESCE(:is_active, true))"
                " ON CONFLICT (name) DO NOTHING"
            ),
            {"name": name, "is_active": item.get("is_active")},
        )
    # `section` is one of the SECTIONS constants, never text from the file, so it is safe in the statement.
    return text(f"INSERT INTO {section} (name) VALUES (:name) ON CONFLICT (name) DO NOTHING"), {"name": name}


if __name__ == "__main__":
    sys.exit(main())
