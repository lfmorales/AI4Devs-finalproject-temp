"""insert the four roles

Revision ID: e5d42817a180
Revises: 35164f01d7a1
Create Date: 2026-11-18 17:10:56.577888

A fresh database gets the four roles from the migrations, without depending on the development seed.
"""
from collections.abc import Sequence

from alembic import op

revision: str = 'e5d42817a180'
down_revision: str | None = '35164f01d7a1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent: a role that already exists, from the seed or an earlier migration, is left as it is.
    op.execute(
        "INSERT INTO roles (name) VALUES ('operations'), ('business'), ('finance'), ('trading')"
        " ON CONFLICT (name) DO NOTHING"
    )
    # A role stored with an explicit id (a restore, for instance) can be ahead of the sequence; leave the sequence at
    # the highest id so a later insert does not collide with it. The table is never empty here.
    op.execute("SELECT setval(pg_get_serial_sequence('roles', 'id'), (SELECT max(id) FROM roles))")


def downgrade() -> None:
    # Nothing to undo: the roles may already be assigned to users, and an assigned role cannot be deleted
    # (user_roles references it with ON DELETE RESTRICT). Removing them would also take away roles that the
    # seed or an administrator created. The trading role keeps its own downgrade, in 35164f01d7a1.
    pass
