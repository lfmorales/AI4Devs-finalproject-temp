"""add the delivery metric to the channels

Revision ID: 8010208e4c15
Revises: f00c04503af9
Create Date: 2026-11-19 19:32:21.869536

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '8010208e4c15'
down_revision: str | None = 'f00c04503af9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('channels', sa.Column('delivery_metric', sa.String(), server_default=sa.text("'impressions'"), nullable=False))
    # Autogenerate does not detect check constraints.
    op.create_check_constraint('ck_channels_delivery_metric', 'channels', "delivery_metric IN ('impressions', 'ots')")
    # DOOH counts its volume in OTS; every other channel keeps the default.
    op.execute("UPDATE channels SET delivery_metric = 'ots' WHERE name = 'DOOH'")


def downgrade() -> None:
    op.drop_constraint('ck_channels_delivery_metric', 'channels', type_='check')
    op.drop_column('channels', 'delivery_metric')
