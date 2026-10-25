"""make campaign lines hang from the campaign

Revision ID: 520fbde04e94
Revises: 3cd42e61ae55
Create Date: 2026-10-25 12:25:55.170190

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '520fbde04e94'
down_revision: str | None = '3cd42e61ae55'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Lines written before the registration used the new model have no campaign, number or dates, and their
    # shape (copies of one line, all under the first period) cannot be reconstructed: refuse, change nothing.
    incomplete = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM campaign_lines WHERE campaign_id IS NULL OR line_number IS NULL"
        " OR start_date IS NULL OR end_date IS NULL"
    )).scalar()
    if incomplete:
        raise RuntimeError(
            f"{incomplete} campaign line(s) have no campaign_id, line_number, start_date or end_date: they predate "
            "the line and flight model and cannot be migrated: recreate the development database "
            "(drop it and run the migrations again)."
        )

    op.alter_column('campaign_lines', 'campaign_id', existing_type=sa.INTEGER(), nullable=False)
    op.alter_column('campaign_lines', 'line_number', existing_type=sa.INTEGER(), nullable=False)
    op.alter_column('campaign_lines', 'start_date', existing_type=sa.DATE(), nullable=False)
    op.alter_column('campaign_lines', 'end_date', existing_type=sa.DATE(), nullable=False)
    op.drop_index(op.f('ix_campaign_lines_campaign_period_id'), table_name='campaign_lines')
    op.drop_constraint(op.f('campaign_lines_campaign_period_id_fkey'), 'campaign_lines', type_='foreignkey')
    op.drop_column('campaign_lines', 'campaign_period_id')


def downgrade() -> None:
    bind = op.get_bind()
    without_flights = bind.execute(sa.text(
        "SELECT count(*) FROM campaign_lines l"
        " WHERE NOT EXISTS (SELECT 1 FROM campaign_line_periods f WHERE f.campaign_line_id = l.id)"
    )).scalar()
    if without_flights:
        raise RuntimeError(
            f"{without_flights} campaign line(s) have no flights, so there is no period to restore for them. "
            "Give every line a flight, or delete the line, before downgrading."
        )

    # Restored from each line's earliest flight, the period the old model would have placed it in.
    op.add_column('campaign_lines', sa.Column('campaign_period_id', sa.INTEGER(), autoincrement=False, nullable=True))
    op.execute(
        "UPDATE campaign_lines l SET campaign_period_id = ("
        " SELECT f.campaign_period_id FROM campaign_line_periods f"
        " WHERE f.campaign_line_id = l.id ORDER BY f.flight_start, f.id LIMIT 1)"
    )
    op.alter_column('campaign_lines', 'campaign_period_id', existing_type=sa.INTEGER(), nullable=False)
    op.create_foreign_key(op.f('campaign_lines_campaign_period_id_fkey'), 'campaign_lines', 'campaign_periods', ['campaign_period_id'], ['id'])
    op.create_index(op.f('ix_campaign_lines_campaign_period_id'), 'campaign_lines', ['campaign_period_id'], unique=False)
    op.alter_column('campaign_lines', 'end_date', existing_type=sa.DATE(), nullable=True)
    op.alter_column('campaign_lines', 'start_date', existing_type=sa.DATE(), nullable=True)
    op.alter_column('campaign_lines', 'line_number', existing_type=sa.INTEGER(), nullable=True)
    op.alter_column('campaign_lines', 'campaign_id', existing_type=sa.INTEGER(), nullable=True)
