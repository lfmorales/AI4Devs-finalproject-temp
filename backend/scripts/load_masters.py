"""Load the master data of a fresh deployment from a JSON file.

Each item is identified by its name and created if it does not exist; nothing existing is modified or deleted.
Everything happens in one transaction. The file is validated before anything is written, and --check stops there.

The output is counts per table. It never carries a name or any other content of the file: a problem in the file is
reported by section and position (for example "agencies[2]: ..."), never by content.

Exit codes: 0 done; 1 the database failed; 2 invalid file or arguments; 3 DATABASE_URL is missing.

Run: python -m scripts.load_masters FILE.json [--check]
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

# Sections in loading order: agencies need their groups first. They are also the table names.
SECTIONS = (
    "holding_groups", "agencies", "advertisers", "dsps", "channels", "formats", "campaign_types", "sectors",
    "sales_reps",
)
# The keys an item may have: exactly the mandatory and optional columns of its table.
_KEYS = {section: {"name"} for section in SECTIONS} | {
    "agencies": {"name", "holding_group"},
    "dsps": {"name", "is_active"},
}
# The ingestion looks the DSP up by this name.
REQUIRED_DSP = "Adform"


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
        arguments = _parse(argv)
    except _InvalidArguments:
        out("status: invalid arguments")
        return EXIT_INVALID

    content, problems = _read(arguments.file)
    if content is not None:
        problems = _check_structure(content)
    if problems or content is None:
        return _reject(problems, out)

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
        problems = _check_references(session, content)
        if problems:
            session.rollback()
            return _reject(problems, out)
        if arguments.check:
            counts = _count_new(session, content)
            session.rollback()
            verb = "would create"
        else:
            counts = {section: _load(session, section, content.get(section, [])) for section in SECTIONS}
            session.commit()
            verb = "created"
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
        out(f"{section}: {verb} {counts[section]}, existing {total - counts[section]}")
    return EXIT_OK


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _Parser(prog="load_masters", description="Load the master data from a JSON file.")
    parser.add_argument("file")
    parser.add_argument("--check", action="store_true", help="validate the file and write nothing")
    return parser.parse_args(argv)


def _reject(problems: list[str], out: Callable[[str], None]) -> int:
    for problem in problems:
        out(f"error: {problem}")
    return EXIT_INVALID


def _read(path: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        with open(path, encoding="utf-8") as handle:
            content = json.load(handle)
    except OSError:
        return None, ["file: cannot be read"]
    except ValueError:  # includes JSONDecodeError and UnicodeDecodeError
        return None, ["file: is not valid JSON"]
    if not isinstance(content, dict):
        return None, ["file: the top level must be an object with one list per section"]
    return content, []


def _name_of(item: Any) -> str | None:
    """The trimmed name of a valid item, or None."""
    if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip():
        return item["name"].strip()
    return None


def _check_structure(content: dict[str, Any]) -> list[str]:
    problems = [f"{section}: unknown section" for section in content if section not in SECTIONS]
    for section in SECTIONS:
        items = content.get(section, [])
        if not isinstance(items, list):
            problems.append(f"{section}: must be a list")
            continue
        seen: set[str] = set()
        for position, item in enumerate(items):
            where = f"{section}[{position}]"
            if not isinstance(item, dict):
                problems.append(f"{where}: must be an object")
                continue
            if set(item) - _KEYS[section]:
                problems.append(f"{where}: unknown key")
            name = _name_of(item)
            if name is None:
                problems.append(f"{where}: name is required")
            elif name in seen:
                problems.append(f"{where}: name is repeated")
            else:
                seen.add(name)
            if section == "agencies" and not _group_of(item):
                problems.append(f"{where}: holding_group is required")
            if section == "dsps" and "is_active" in item and not isinstance(item["is_active"], bool):
                problems.append(f"{where}: is_active must be true or false")
    return problems


def _group_of(item: dict[str, Any]) -> str | None:
    group = item.get("holding_group")
    return group.strip() if isinstance(group, str) and group.strip() else None


def _check_references(session: Session, content: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    stored_groups = {row[0] for row in session.execute(text("SELECT name FROM holding_groups"))}
    file_groups = {name for item in content.get("holding_groups", []) if (name := _name_of(item))}
    for position, item in enumerate(content.get("agencies", [])):
        group = _group_of(item) if isinstance(item, dict) else None
        if group is not None and group not in file_groups | stored_groups:
            problems.append(f"agencies[{position}]: the holding group is neither in the file nor stored")

    file_dsps = {name for item in content.get("dsps", []) if (name := _name_of(item))}
    stored_adform = session.execute(text("SELECT 1 FROM dsps WHERE name = :name"), {"name": REQUIRED_DSP}).first()
    if REQUIRED_DSP not in file_dsps and stored_adform is None:
        problems.append(f"dsps: a DSP named {REQUIRED_DSP} is required, in the file or already stored")
    return problems


def _count_new(session: Session, content: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for section in SECTIONS:
        # `section` is one of the SECTIONS constants, never text from the file, so it is safe in the statement.
        stored = {row[0] for row in session.execute(text(f"SELECT name FROM {section}"))}
        counts[section] = sum(1 for item in content.get(section, []) if _name_of(item) not in stored)
    return counts


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
    return text(f"INSERT INTO {section} (name) VALUES (:name) ON CONFLICT (name) DO NOTHING"), {"name": name}


if __name__ == "__main__":
    sys.exit(main())
