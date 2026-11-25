"""add the closing headers and the snapshot of every closed flight

A closed flight is read from its snapshot from now on. The snapshot of a flight closed before this migration cannot be
rebuilt, because the delivery of the moment it was closed is no longer stored, so the migration refuses a database that
holds closed flights instead of backfilling them. There is no production yet; a development database is reset with
e2e/scripts/reset-data.sh.

Revision ID: 3a08cce1c979
Revises: 950895fa2d75
Create Date: 2026-11-25 18:52:06.903226

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '3a08cce1c979'
down_revision: str | None = '950895fa2d75'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Added once, never changed or deleted, like the applied rates: the function comes from the margin migration.
_APPEND_ONLY_TABLES = ("month_closings", "month_closing_batches", "closed_flight_snapshots")
_CLOSED_FLIGHTS_FOUND = (
    "applied_rates holds flights closed before the closing snapshot existed, and this migration cannot build their "
    "snapshot: the delivery they were closed with is no longer stored. Reset the database with "
    "e2e/scripts/reset-data.sh and run the migrations again."
)


def upgrade() -> None:
    # Before any DDL, so a refused database is left exactly as it was.
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM applied_rates)")).scalar():
        raise RuntimeError(_CLOSED_FLIGHTS_FOUND)

    op.create_table('month_closings',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('period_year', sa.Integer(), nullable=False),
    sa.Column('period_month', sa.SmallInteger(), nullable=False),
    sa.Column('closed_at', sa.DateTime(), nullable=False),
    sa.Column('closed_by', sa.Integer(), nullable=False),
    sa.Column('as_of', sa.Date(), nullable=False),
    sa.CheckConstraint('period_month BETWEEN 1 AND 12', name='ck_month_closings_period_month'),
    sa.ForeignKeyConstraint(['closed_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_month_closings_period', 'month_closings', ['period_year', 'period_month'], unique=False)
    op.create_table('month_closing_batches',
    sa.Column('month_closing_id', sa.BigInteger(), nullable=False),
    sa.Column('dsp_id', sa.Integer(), nullable=False),
    sa.Column('ingestion_batch_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['dsp_id'], ['dsps.id'], ),
    sa.ForeignKeyConstraint(['ingestion_batch_id'], ['ingestion_batches.id'], ),
    sa.ForeignKeyConstraint(['month_closing_id'], ['month_closings.id'], ),
    sa.PrimaryKeyConstraint('month_closing_id', 'dsp_id')
    )
    op.create_table('closed_flight_snapshots',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('applied_rate_id', sa.BigInteger(), nullable=False),
    sa.Column('month_closing_id', sa.BigInteger(), nullable=False),
    sa.Column('revenue', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('contracted_revenue', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('media_cost', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('rebate', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('platform_cost', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('margin', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('gross_revenue', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('delivered_impressions', sa.BigInteger(), nullable=False),
    sa.Column('delivered', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('window_media_cost', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('window_reported_revenue', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('window_buyer_spend', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('window_data_cost', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('gross_differs_from_buyer_spend', sa.Boolean(), nullable=False),
    sa.Column('data_cost_reported', sa.Boolean(), nullable=False),
    sa.Column('delivery_metric', sa.String(), nullable=False),
    sa.Column('sale_cpm', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('contracted_impressions', sa.BigInteger(), nullable=False),
    sa.Column('volume_commitment', sa.String(), nullable=False),
    sa.CheckConstraint("(volume_commitment = 'target') = (gross_revenue IS NOT NULL)", name='ck_closed_flight_snapshots_gross_with_target'),
    sa.CheckConstraint("delivery_metric IN ('impressions', 'ots')", name='ck_closed_flight_snapshots_delivery_metric'),
    sa.CheckConstraint("volume_commitment IN ('committed', 'target')", name='ck_closed_flight_snapshots_volume_commitment'),
    sa.ForeignKeyConstraint(['applied_rate_id'], ['applied_rates.id'], ),
    sa.ForeignKeyConstraint(['month_closing_id'], ['month_closings.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('applied_rate_id')
    )
    op.create_index(op.f('ix_closed_flight_snapshots_month_closing_id'), 'closed_flight_snapshots', ['month_closing_id'], unique=False)
    for table in _APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_append_only_change()"
        )


def downgrade() -> None:
    for table in _APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.drop_index(op.f('ix_closed_flight_snapshots_month_closing_id'), table_name='closed_flight_snapshots')
    op.drop_table('closed_flight_snapshots')
    op.drop_table('month_closing_batches')
    op.drop_index('ix_month_closings_period', table_name='month_closings')
    op.drop_table('month_closings')
