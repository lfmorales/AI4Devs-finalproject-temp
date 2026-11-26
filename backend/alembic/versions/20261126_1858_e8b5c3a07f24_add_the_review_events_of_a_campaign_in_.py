"""add the review events of a campaign in a month

Only the events are stored: a review, and a reopening that returns the campaign to pending review, with its cause and,
for the three edits that reopen a review, the flight they changed. The state of a campaign is derived. The table is
append-only, with the trigger of the closing's tables, whose function comes from the margin migration.

Revision ID: e8b5c3a07f24
Revises: d7e2a9f41b36
Create Date: 2026-11-26 18:58:30.589638

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'e8b5c3a07f24'
down_revision: str | None = 'd7e2a9f41b36'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('campaign_period_reviews',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('campaign_period_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('cause', sa.String(length=24), nullable=True),
    sa.Column('campaign_line_period_id', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("COALESCE(cause IN ('adjustment', 'carryover', 'carryover_billable'), false) = (campaign_line_period_id IS NOT NULL)", name='ck_campaign_period_reviews_flight_with_edit'),
    sa.CheckConstraint("(kind = 'reviewed') = (cause IS NULL)", name='ck_campaign_period_reviews_cause_with_reopening'),
    sa.CheckConstraint("cause IS NULL OR cause IN ('withdrawn', 'adjustment', 'carryover', 'carryover_billable')", name='ck_campaign_period_reviews_cause'),
    sa.CheckConstraint("kind IN ('reviewed', 'reopened')", name='ck_campaign_period_reviews_kind'),
    sa.ForeignKeyConstraint(['campaign_line_period_id'], ['campaign_line_periods.id'], ),
    sa.ForeignKeyConstraint(['campaign_period_id'], ['campaign_periods.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_campaign_period_reviews_period', 'campaign_period_reviews', ['campaign_period_id', 'id'], unique=False)
    op.execute(
        "CREATE TRIGGER campaign_period_reviews_append_only BEFORE UPDATE OR DELETE ON campaign_period_reviews "
        "FOR EACH ROW EXECUTE FUNCTION reject_append_only_change()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER campaign_period_reviews_append_only ON campaign_period_reviews")
    op.drop_index('ix_campaign_period_reviews_period', table_name='campaign_period_reviews')
    op.drop_table('campaign_period_reviews')
