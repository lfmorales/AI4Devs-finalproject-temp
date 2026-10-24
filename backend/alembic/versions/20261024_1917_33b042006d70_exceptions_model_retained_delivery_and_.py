"""exceptions model retained delivery and zero unmatched count

Revision ID: 33b042006d70
Revises: 762354975e91
Create Date: 2026-10-24 19:17:06.620950

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '33b042006d70'
down_revision: str | None = '762354975e91'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_OLD_TYPES = (("delivery_without_line", "unmatched_delivery"), ("line_without_delivery", "missing_delivery"))

_CHECKS = {
    "ck_ingestion_exceptions_unmatched_fields": (
        "exception_type <> 'unmatched_delivery' OR (dsp_id IS NOT NULL AND external_campaign_id IS NOT NULL "
        "AND external_line_item_id IS NOT NULL)"
    ),
    "ck_ingestion_exceptions_missing_fields": (
        "exception_type <> 'missing_delivery' OR (campaign_line_id IS NOT NULL AND campaign_period_id IS NOT NULL)"
    ),
    "ck_ingestion_exceptions_resolution_fields": (
        "(status = 'open' AND resolved_at IS NULL AND resolved_by IS NULL) OR "
        "(status = 'resolved' AND resolved_at IS NOT NULL AND resolved_by IS NOT NULL)"
    ),
}


def upgrade() -> None:
    # No run has produced an exception before this migration, so there are no rows to convert. If one existed,
    # the check constraints below would reject it loudly rather than leave an exception without its pair.
    for old_name, new_name in _OLD_TYPES:
        op.execute(f"ALTER TYPE ingestion_exception_type_enum RENAME VALUE '{old_name}' TO '{new_name}'")

    op.create_table('ingestion_exception_deliveries',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('exception_id', sa.Integer(), nullable=False),
    sa.Column('delivery_date', sa.Date(), nullable=False),
    sa.Column('impressions', sa.BigInteger(), nullable=False),
    sa.Column('clicks', sa.BigInteger(), nullable=False),
    sa.Column('media_cost', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('measurable_impressions', sa.BigInteger(), nullable=False),
    sa.Column('viewable_impressions', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['exception_id'], ['ingestion_exceptions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('exception_id', 'delivery_date', name='uq_exception_deliveries_exception_date')
    )
    op.add_column('ingestion_batches', sa.Column('zero_unmatched_row_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('ingestion_exceptions', sa.Column('campaign_period_id', sa.Integer(), nullable=True))
    op.add_column('ingestion_exceptions', sa.Column('dsp_id', sa.Integer(), nullable=True))
    op.add_column('ingestion_exceptions', sa.Column('external_campaign_id', sa.String(), nullable=True))
    op.add_column('ingestion_exceptions', sa.Column('external_line_item_id', sa.String(), nullable=True))
    op.add_column('ingestion_exceptions', sa.Column('first_date', sa.Date(), nullable=True))
    op.add_column('ingestion_exceptions', sa.Column('last_date', sa.Date(), nullable=True))
    op.add_column('ingestion_exceptions', sa.Column('resolved_at', sa.DateTime(), nullable=True))
    op.add_column('ingestion_exceptions', sa.Column('resolved_by', sa.Integer(), nullable=True))
    op.add_column('ingestion_exceptions', sa.Column('note', sa.String(), nullable=True))
    op.create_foreign_key('fk_ingestion_exceptions_campaign_period_id', 'ingestion_exceptions', 'campaign_periods', ['campaign_period_id'], ['id'])
    op.create_foreign_key('fk_ingestion_exceptions_resolved_by', 'ingestion_exceptions', 'users', ['resolved_by'], ['id'])
    op.create_foreign_key('fk_ingestion_exceptions_dsp_id', 'ingestion_exceptions', 'dsps', ['dsp_id'], ['id'])
    op.drop_column('ingestion_exceptions', 'external_key')
    for name, condition in _CHECKS.items():
        op.create_check_constraint(name, 'ingestion_exceptions', condition)
    op.create_index('uq_ingestion_exceptions_missing_line_period', 'ingestion_exceptions', ['campaign_line_id', 'campaign_period_id'], unique=True, postgresql_where=sa.text("exception_type = 'missing_delivery'"))
    op.create_index('uq_ingestion_exceptions_unmatched_pair', 'ingestion_exceptions', ['exception_type', 'dsp_id', 'external_campaign_id', 'external_line_item_id'], unique=True, postgresql_where=sa.text("exception_type = 'unmatched_delivery'"))


def downgrade() -> None:
    op.drop_index('uq_ingestion_exceptions_unmatched_pair', table_name='ingestion_exceptions', postgresql_where=sa.text("exception_type = 'unmatched_delivery'"))
    op.drop_index('uq_ingestion_exceptions_missing_line_period', table_name='ingestion_exceptions', postgresql_where=sa.text("exception_type = 'missing_delivery'"))
    for name in _CHECKS:
        op.drop_constraint(name, 'ingestion_exceptions', type_='check')
    # The old key was one text column; rebuild it from the pair so the NOT NULL can be restored.
    op.add_column('ingestion_exceptions', sa.Column('external_key', sa.VARCHAR(), nullable=True))
    op.execute("UPDATE ingestion_exceptions SET external_key = COALESCE(external_campaign_id || '/' || external_line_item_id, '')")
    op.alter_column('ingestion_exceptions', 'external_key', nullable=False)
    op.drop_constraint('fk_ingestion_exceptions_dsp_id', 'ingestion_exceptions', type_='foreignkey')
    op.drop_constraint('fk_ingestion_exceptions_resolved_by', 'ingestion_exceptions', type_='foreignkey')
    op.drop_constraint('fk_ingestion_exceptions_campaign_period_id', 'ingestion_exceptions', type_='foreignkey')
    op.drop_column('ingestion_exceptions', 'note')
    op.drop_column('ingestion_exceptions', 'resolved_by')
    op.drop_column('ingestion_exceptions', 'resolved_at')
    op.drop_column('ingestion_exceptions', 'last_date')
    op.drop_column('ingestion_exceptions', 'first_date')
    op.drop_column('ingestion_exceptions', 'external_line_item_id')
    op.drop_column('ingestion_exceptions', 'external_campaign_id')
    op.drop_column('ingestion_exceptions', 'dsp_id')
    op.drop_column('ingestion_exceptions', 'campaign_period_id')
    op.drop_column('ingestion_batches', 'zero_unmatched_row_count')
    op.drop_table('ingestion_exception_deliveries')
    for old_name, new_name in _OLD_TYPES:
        op.execute(f"ALTER TYPE ingestion_exception_type_enum RENAME VALUE '{new_name}' TO '{old_name}'")
