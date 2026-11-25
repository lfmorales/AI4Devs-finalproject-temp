"""add the frozen revenue and rebate base to the applied rates

Revision ID: 950895fa2d75
Revises: 763931a4d704
Create Date: 2026-11-25 09:59:37.420139

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '950895fa2d75'
down_revision: str | None = '763931a4d704'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The revenue a target flight's DSP reported and the gross its rebate was priced on, frozen at closing. Nullable
    # with no default: every row stored so far is a committed flight, which holds neither, and the rows of
    # applied_rates are never updated, so adding the columns writes nothing to them.
    op.add_column('applied_rates', sa.Column('revenue_amount', sa.Numeric(precision=24, scale=12), nullable=True))
    op.add_column('applied_rates', sa.Column('rebate_base_amount', sa.Numeric(precision=24, scale=12), nullable=True))
    # Not detected by autogenerate on an existing table: both null or both set.
    op.create_check_constraint(
        'ck_applied_rates_frozen_revenue_and_base_together',
        'applied_rates',
        '(revenue_amount IS NULL) = (rebate_base_amount IS NULL)',
    )


def downgrade() -> None:
    op.drop_constraint('ck_applied_rates_frozen_revenue_and_base_together', 'applied_rates', type_='check')
    op.drop_column('applied_rates', 'rebate_base_amount')
    op.drop_column('applied_rates', 'revenue_amount')
