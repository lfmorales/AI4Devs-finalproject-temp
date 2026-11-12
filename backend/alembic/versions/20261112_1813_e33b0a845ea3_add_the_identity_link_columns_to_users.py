"""add the identity link columns to users

Revision ID: e33b0a845ea3
Revises: 439b6b8481f8
Create Date: 2026-11-12 18:13:31.160043

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'e33b0a845ea3'
down_revision: str | None = '439b6b8481f8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('identity_issuer', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('identity_subject', sa.String(length=255), nullable=True))
    op.create_unique_constraint('uq_users_identity_issuer_subject', 'users', ['identity_issuer', 'identity_subject'])
    # Not detected by autogenerate. Existing rows have both columns NULL, so they satisfy it.
    op.create_check_constraint(
        'ck_users_identity_pair_complete', 'users', '(identity_issuer IS NULL) = (identity_subject IS NULL)'
    )


def downgrade() -> None:
    op.drop_constraint('ck_users_identity_pair_complete', 'users', type_='check')
    op.drop_constraint('uq_users_identity_issuer_subject', 'users', type_='unique')
    op.drop_column('users', 'identity_subject')
    op.drop_column('users', 'identity_issuer')
