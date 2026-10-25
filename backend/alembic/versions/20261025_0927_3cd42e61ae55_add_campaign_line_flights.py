"""add campaign line flights

Revision ID: 3cd42e61ae55
Revises: 33b042006d70
Create Date: 2026-10-25 09:27:54.940789

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '3cd42e61ae55'
down_revision: str | None = '33b042006d70'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('campaign_line_periods',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('campaign_line_id', sa.Integer(), nullable=False),
    sa.Column('campaign_period_id', sa.Integer(), nullable=False),
    sa.Column('flight_start', sa.Date(), nullable=False),
    sa.Column('flight_end', sa.Date(), nullable=False),
    sa.Column('contracted_impressions', sa.BigInteger(), nullable=False),
    sa.CheckConstraint('flight_start <= flight_end', name='ck_campaign_line_periods_window_order'),
    sa.ForeignKeyConstraint(['campaign_line_id'], ['campaign_lines.id'], ),
    sa.ForeignKeyConstraint(['campaign_period_id'], ['campaign_periods.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('campaign_line_id', 'campaign_period_id', name='uq_campaign_line_periods_line_period')
    )
    op.create_index(op.f('ix_campaign_line_periods_campaign_period_id'), 'campaign_line_periods', ['campaign_period_id'], unique=False)
    op.add_column('campaign_lines', sa.Column('campaign_id', sa.Integer(), nullable=True))
    op.add_column('campaign_lines', sa.Column('line_number', sa.Integer(), nullable=True))
    op.add_column('campaign_lines', sa.Column('start_date', sa.Date(), nullable=True))
    op.add_column('campaign_lines', sa.Column('end_date', sa.Date(), nullable=True))
    op.create_index('uq_campaign_lines_campaign_line_number', 'campaign_lines', ['campaign_id', 'line_number'], unique=True, postgresql_where=sa.text('campaign_id IS NOT NULL AND line_number IS NOT NULL'))
    op.create_foreign_key('fk_campaign_lines_campaign_id', 'campaign_lines', 'campaigns', ['campaign_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_campaign_lines_campaign_id', 'campaign_lines', type_='foreignkey')
    op.drop_index('uq_campaign_lines_campaign_line_number', table_name='campaign_lines', postgresql_where=sa.text('campaign_id IS NOT NULL AND line_number IS NOT NULL'))
    op.drop_column('campaign_lines', 'end_date')
    op.drop_column('campaign_lines', 'start_date')
    op.drop_column('campaign_lines', 'line_number')
    op.drop_column('campaign_lines', 'campaign_id')
    op.drop_index(op.f('ix_campaign_line_periods_campaign_period_id'), table_name='campaign_line_periods')
    op.drop_table('campaign_line_periods')
