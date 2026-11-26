"""add the billing adjustments of a flight

A manual adjustment of a committed flight's billing: its basis, its amount (only for `custom`), its reason, its author
and its moment. Rows are only added and the latest of a flight is in force, so the table gets the append-only trigger of
the closing's tables, whose function comes from the margin migration. The checks are generated from the model.

Revision ID: d7e2a9f41b36
Revises: c4a1b7e92d10
Create Date: 2026-11-26 18:38:41.555457

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'd7e2a9f41b36'
down_revision: str | None = 'c4a1b7e92d10'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('flight_billing_adjustments',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('campaign_line_period_id', sa.Integer(), nullable=False),
    sa.Column('basis', sa.String(length=16), nullable=False),
    sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(basis = 'custom') = (amount IS NOT NULL)", name='ck_flight_billing_adjustments_amount_with_custom'),
    sa.CheckConstraint("basis IN ('minimum', 'delivered', 'contracted', 'custom')", name='ck_flight_billing_adjustments_basis'),
    sa.CheckConstraint('amount IS NULL OR amount >= 0', name='ck_flight_billing_adjustments_amount_not_negative'),
    sa.CheckConstraint('length(btrim(reason)) > 0', name='ck_flight_billing_adjustments_reason_not_blank'),
    sa.ForeignKeyConstraint(['campaign_line_period_id'], ['campaign_line_periods.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_flight_billing_adjustments_flight', 'flight_billing_adjustments', ['campaign_line_period_id', 'id'], unique=False)
    op.execute(
        "CREATE TRIGGER flight_billing_adjustments_append_only BEFORE UPDATE OR DELETE ON flight_billing_adjustments "
        "FOR EACH ROW EXECUTE FUNCTION reject_append_only_change()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER flight_billing_adjustments_append_only ON flight_billing_adjustments")
    op.drop_index('ix_flight_billing_adjustments_flight', table_name='flight_billing_adjustments')
    op.drop_table('flight_billing_adjustments')
