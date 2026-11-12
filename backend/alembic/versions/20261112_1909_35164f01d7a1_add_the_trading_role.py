"""add the trading role

Revision ID: 35164f01d7a1
Revises: e33b0a845ea3
Create Date: 2026-11-12 19:09:08.348717

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '35164f01d7a1'
down_revision: str | None = 'e33b0a845ea3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("INSERT INTO roles (name) VALUES ('trading') ON CONFLICT (name) DO NOTHING")


def downgrade() -> None:
    # The assignments reference the role with ON DELETE RESTRICT, so they go first.
    op.execute("DELETE FROM user_roles WHERE role_id IN (SELECT id FROM roles WHERE name = 'trading')")
    op.execute("DELETE FROM roles WHERE name = 'trading'")
