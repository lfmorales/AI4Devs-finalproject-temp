"""add the volume commitment to the campaign lines

Revision ID: 273c50da57b0
Revises: 8010208e4c15
Create Date: 2026-11-24 11:38:32.566223

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '273c50da57b0'
down_revision: str | None = '8010208e4c15'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The default fills every existing line: they were all registered as committed volume.
    op.add_column('campaign_lines', sa.Column('volume_commitment', sa.String(), server_default=sa.text("'committed'"), nullable=False))
    # Autogenerate does not detect check constraints.
    op.create_check_constraint(
        'ck_campaign_lines_volume_commitment', 'campaign_lines', "volume_commitment IN ('committed', 'target')"
    )


def downgrade() -> None:
    op.drop_constraint('ck_campaign_lines_volume_commitment', 'campaign_lines', type_='check')
    op.drop_column('campaign_lines', 'volume_commitment')
