"""add the frozen billing to the snapshot of a closed flight

A closing freezes, beside the revenue it already froze, how the billing was reached (its basis), the volume it was
billed on, the carry-over the flight had received and whether it was billable, and the adjustment in force. A snapshot
written before this migration keeps the five columns null: its flight keeps the revenue it was closed with, so nothing is
refused or backfilled. The table is append-only; adding columns writes no row. The checks are added by hand: Alembic does
not detect them.

Revision ID: f1c6d2b84a57
Revises: e8b5c3a07f24
Create Date: 2026-11-26 19:19:31.698792

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'f1c6d2b84a57'
down_revision: str | None = 'e8b5c3a07f24'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE = 'closed_flight_snapshots'
_FOREIGN_KEY = 'closed_flight_snapshots_billing_adjustment_id_fkey'
_CHECKS = {
    'ck_closed_flight_snapshots_billing_together': (
        '(billing_basis IS NULL) = (carryover IS NULL) AND (billing_basis IS NULL) = (carryover_billable IS NULL)'
        ' AND (billing_basis IS NOT NULL OR (billable IS NULL AND billing_adjustment_id IS NULL))'
    ),
    'ck_closed_flight_snapshots_billing_basis': (
        "billing_basis IS NULL OR billing_basis IN ('minimum', 'delivered', 'contracted', 'custom', 'reported')"
    ),
    'ck_closed_flight_snapshots_reported_with_target': (
        "billing_basis IS NULL OR (billing_basis = 'reported') = (volume_commitment = 'target')"
    ),
    'ck_closed_flight_snapshots_billable_with_volume_basis': (
        "(billing_basis IN ('minimum', 'delivered', 'contracted')) = (billable IS NOT NULL)"
    ),
    'ck_closed_flight_snapshots_adjustment_with_adjusted_basis': (
        "billing_basis NOT IN ('delivered', 'contracted', 'custom') OR billing_adjustment_id IS NOT NULL"
    ),
    'ck_closed_flight_snapshots_carryover_not_negative': 'carryover IS NULL OR carryover >= 0',
}


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column('billing_basis', sa.String(length=16), nullable=True))
    op.add_column(_TABLE, sa.Column('billable', sa.Numeric(precision=18, scale=4), nullable=True))
    op.add_column(_TABLE, sa.Column('carryover', sa.BigInteger(), nullable=True))
    op.add_column(_TABLE, sa.Column('carryover_billable', sa.Boolean(), nullable=True))
    op.add_column(_TABLE, sa.Column('billing_adjustment_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key(_FOREIGN_KEY, _TABLE, 'flight_billing_adjustments', ['billing_adjustment_id'], ['id'])
    for name, condition in _CHECKS.items():
        op.create_check_constraint(name, _TABLE, condition)


def downgrade() -> None:
    for name in _CHECKS:
        op.drop_constraint(name, _TABLE, type_='check')
    op.drop_constraint(_FOREIGN_KEY, _TABLE, type_='foreignkey')
    op.drop_column(_TABLE, 'billing_adjustment_id')
    op.drop_column(_TABLE, 'carryover_billable')
    op.drop_column(_TABLE, 'carryover')
    op.drop_column(_TABLE, 'billable')
    op.drop_column(_TABLE, 'billing_basis')
