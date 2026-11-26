"""add the carry-over of a flight

The volume a flight received from the previous flight of its line, why, who wrote it and when, and whether it is
billable (campaign/carryover). Every flight that exists gets no carry-over and a flag of false, so nothing changes for
it. The contracted volume is never touched. The checks are added by hand: Alembic does not detect them.

Revision ID: c4a1b7e92d10
Revises: 3a08cce1c979
Create Date: 2026-11-26 17:57:51.191332

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'c4a1b7e92d10'
down_revision: str | None = '3a08cce1c979'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = 'campaign_line_periods'
_CHECKS = {
    'ck_campaign_line_periods_carryover_not_negative': 'carryover >= 0',
    'ck_campaign_line_periods_carryover_is_accounted_for': (
        'carryover = 0 OR (carryover_reason IS NOT NULL AND length(btrim(carryover_reason)) > 0'
        ' AND carryover_set_by IS NOT NULL AND carryover_set_at IS NOT NULL)'
    ),
    'ck_campaign_line_periods_carryover_billable_is_accounted_for': (
        'NOT carryover_billable OR (carryover_billable_set_by IS NOT NULL AND carryover_billable_set_at IS NOT NULL)'
    ),
}


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column('carryover', sa.BigInteger(), server_default=sa.text('0'), nullable=False))
    op.add_column(_TABLE, sa.Column('carryover_reason', sa.Text(), nullable=True))
    op.add_column(_TABLE, sa.Column('carryover_set_by', sa.Integer(), nullable=True))
    op.add_column(_TABLE, sa.Column('carryover_set_at', sa.DateTime(), nullable=True))
    op.add_column(_TABLE, sa.Column('carryover_billable', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column(_TABLE, sa.Column('carryover_billable_set_by', sa.Integer(), nullable=True))
    op.add_column(_TABLE, sa.Column('carryover_billable_set_at', sa.DateTime(), nullable=True))
    op.create_foreign_key('campaign_line_periods_carryover_set_by_fkey', _TABLE, 'users', ['carryover_set_by'], ['id'])
    op.create_foreign_key(
        'campaign_line_periods_carryover_billable_set_by_fkey', _TABLE, 'users', ['carryover_billable_set_by'], ['id']
    )
    for name, condition in _CHECKS.items():
        op.create_check_constraint(name, _TABLE, condition)


def downgrade() -> None:
    for name in _CHECKS:
        op.drop_constraint(name, _TABLE, type_='check')
    op.drop_constraint('campaign_line_periods_carryover_billable_set_by_fkey', _TABLE, type_='foreignkey')
    op.drop_constraint('campaign_line_periods_carryover_set_by_fkey', _TABLE, type_='foreignkey')
    op.drop_column(_TABLE, 'carryover_billable_set_at')
    op.drop_column(_TABLE, 'carryover_billable_set_by')
    op.drop_column(_TABLE, 'carryover_billable')
    op.drop_column(_TABLE, 'carryover_set_at')
    op.drop_column(_TABLE, 'carryover_set_by')
    op.drop_column(_TABLE, 'carryover_reason')
    op.drop_column(_TABLE, 'carryover')
