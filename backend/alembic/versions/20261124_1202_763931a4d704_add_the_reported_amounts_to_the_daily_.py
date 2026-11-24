"""add the reported amounts to the daily deliveries

Revision ID: 763931a4d704
Revises: 273c50da57b0
Create Date: 2026-11-24 12:02:22.959251

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '763931a4d704'
down_revision: str | None = '273c50da57b0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # What a DSP such as Equativ bills next to the delivery. The zero default fills every existing row: Adform reports
    # none of the four, and every row stored so far came from Adform.
    op.add_column('daily_deliveries', sa.Column('buyer_spend', sa.Numeric(precision=18, scale=6), server_default=sa.text('0'), nullable=False))
    op.add_column('daily_deliveries', sa.Column('reported_revenue', sa.Numeric(precision=18, scale=6), server_default=sa.text('0'), nullable=False))
    op.add_column('daily_deliveries', sa.Column('third_party_data_cost', sa.Numeric(precision=18, scale=6), server_default=sa.text('0'), nullable=False))
    op.add_column('daily_deliveries', sa.Column('audience_data_cost', sa.Numeric(precision=18, scale=6), server_default=sa.text('0'), nullable=False))


def downgrade() -> None:
    op.drop_column('daily_deliveries', 'audience_data_cost')
    op.drop_column('daily_deliveries', 'third_party_data_cost')
    op.drop_column('daily_deliveries', 'reported_revenue')
    op.drop_column('daily_deliveries', 'buyer_spend')
