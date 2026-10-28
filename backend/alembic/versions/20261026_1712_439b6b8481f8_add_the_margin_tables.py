"""add the margin tables

Rebate schedules and brackets, platform rate settings, and the rates frozen when a month is closed.
Needs the btree_gist extension for the rule that two schedules of one key never overlap (see docs/deploy.md).

Revision ID: 439b6b8481f8
Revises: e6a29ae62e94
Create Date: 2026-10-26 17:12:59.238139

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

_EXTENSION_MARKER = "btree_gist was created by the margin migration"
_APPEND_ONLY_TABLES = ("applied_rates", "applied_rate_brackets")

revision: str = '439b6b8481f8'
down_revision: str | None = 'e6a29ae62e94'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ensure_btree_gist() -> bool:
    """Make sure the extension exists; say clearly what to do if it cannot be created. True if created here."""
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'btree_gist'")).scalar():
        return False
    try:
        with connection.begin_nested():
            connection.execute(sa.text("CREATE EXTENSION btree_gist"))
    except sa.exc.DBAPIError:
        raise RuntimeError(
            "The margin migration needs the PostgreSQL extension btree_gist and this database user cannot create it. "
            "Ask an administrator to run CREATE EXTENSION btree_gist; and run the migration again. "
            "See docs/deploy.md."
        ) from None
    return True


def upgrade() -> None:
    created_extension = _ensure_btree_gist()
    op.create_table('rebate_schedules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('holding_group_id', sa.Integer(), nullable=False),
    sa.Column('agency_id', sa.Integer(), nullable=True),
    sa.Column('channel_id', sa.Integer(), nullable=True),
    sa.Column('scope', postgresql.ENUM('national', 'international', name='scope_enum', create_type=False), nullable=True),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True),
    postgresql.ExcludeConstraint((sa.column('holding_group_id'), '='), (sa.text('coalesce(agency_id, 0)'), '='), (sa.text('coalesce(channel_id, 0)'), '='), (sa.text('(scope IS NULL)'), '='), (sa.text("coalesce(scope, 'national'::scope_enum)"), '='), (sa.text("daterange(valid_from, valid_to, '[]')"), '&&'), using='gist', name='ex_rebate_schedules_key_validity'),
    sa.CheckConstraint('valid_to IS NULL OR valid_from <= valid_to', name='ck_rebate_schedules_validity_order'),
    sa.ForeignKeyConstraint(['agency_id'], ['agencies.id'], ),
    sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ),
    sa.ForeignKeyConstraint(['holding_group_id'], ['holding_groups.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('rebate_brackets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rebate_schedule_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('lower', sa.Numeric(precision=24, scale=12), nullable=False),
    sa.Column('upper', sa.Numeric(precision=24, scale=12), nullable=True),
    sa.Column('rate', sa.Numeric(precision=20, scale=12), nullable=False),
    sa.CheckConstraint('lower >= 0', name='ck_rebate_brackets_lower_not_negative'),
    sa.CheckConstraint('rate >= 0', name='ck_rebate_brackets_rate_not_negative'),
    sa.CheckConstraint('upper IS NULL OR upper > lower', name='ck_rebate_brackets_upper_above_lower'),
    sa.ForeignKeyConstraint(['rebate_schedule_id'], ['rebate_schedules.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('rebate_schedule_id', 'position', name='uq_rebate_brackets_schedule_position')
    )
    op.create_table('platform_rate_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('campaign_line_id', sa.Integer(), nullable=True),
    sa.Column('agency_id', sa.Integer(), nullable=True),
    sa.Column('campaign_type_id', sa.Integer(), nullable=True),
    sa.Column('rate_per_thousand', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(level = 'line' AND campaign_line_id IS NOT NULL AND agency_id IS NULL AND campaign_type_id IS NULL) OR (level = 'agency' AND agency_id IS NOT NULL AND campaign_line_id IS NULL AND campaign_type_id IS NULL) OR (level = 'campaign_type' AND campaign_type_id IS NOT NULL AND campaign_line_id IS NULL AND agency_id IS NULL) OR (level = 'system' AND campaign_line_id IS NULL AND agency_id IS NULL AND campaign_type_id IS NULL)", name='ck_platform_rate_settings_level_key'),
    sa.CheckConstraint("level = 'system' OR created_by IS NOT NULL", name='ck_platform_rate_settings_author'),
    sa.CheckConstraint("level IN ('line', 'agency', 'campaign_type', 'system')", name='ck_platform_rate_settings_level'),
    sa.CheckConstraint('rate_per_thousand >= 0', name='ck_platform_rate_settings_rate_not_negative'),
    sa.ForeignKeyConstraint(['agency_id'], ['agencies.id'], ),
    sa.ForeignKeyConstraint(['campaign_line_id'], ['campaign_lines.id'], ),
    sa.ForeignKeyConstraint(['campaign_type_id'], ['campaign_types.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_platform_rate_settings_level', 'platform_rate_settings', ['level'], unique=False)
    op.create_table('applied_rates',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('campaign_line_period_id', sa.Integer(), nullable=False),
    sa.Column('rebate_schedule_id', sa.Integer(), nullable=True),
    sa.Column('ladder_step', sa.SmallInteger(), nullable=False),
    sa.Column('source_year', sa.Integer(), nullable=True),
    sa.Column('agency_exception', sa.Boolean(), nullable=False),
    sa.Column('zero_reason', sa.String(length=32), nullable=True),
    sa.Column('effective_rate', sa.Numeric(precision=20, scale=12), nullable=False),
    sa.Column('counter_group_id', sa.Integer(), nullable=False),
    sa.Column('counter_agency_id', sa.Integer(), nullable=True),
    sa.Column('counter_channel_id', sa.Integer(), nullable=False),
    sa.Column('counter_year', sa.Integer(), nullable=False),
    sa.Column('position_before', sa.Numeric(precision=24, scale=12), nullable=False),
    sa.Column('position_after', sa.Numeric(precision=24, scale=12), nullable=False),
    sa.Column('rebate_amount', sa.Numeric(precision=24, scale=12), nullable=False),
    sa.Column('platform_rate', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('closed_at', sa.DateTime(), nullable=False),
    sa.Column('closed_by', sa.Integer(), nullable=False),
    sa.CheckConstraint("zero_reason IS NULL OR zero_reason IN ('no_schedule', 'no_schedule_for_year')", name='ck_applied_rates_zero_reason'),
    sa.CheckConstraint('ladder_step IN (1, 2, 3, 4, 5, 6, 8)', name='ck_applied_rates_ladder_step'),
    sa.CheckConstraint('platform_rate >= 0', name='ck_applied_rates_platform_rate_not_negative'),
    sa.ForeignKeyConstraint(['campaign_line_period_id'], ['campaign_line_periods.id'], ),
    sa.ForeignKeyConstraint(['closed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['counter_agency_id'], ['agencies.id'], ),
    sa.ForeignKeyConstraint(['counter_channel_id'], ['channels.id'], ),
    sa.ForeignKeyConstraint(['counter_group_id'], ['holding_groups.id'], ),
    sa.ForeignKeyConstraint(['rebate_schedule_id'], ['rebate_schedules.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('campaign_line_period_id')
    )
    op.create_index('ix_applied_rates_counter', 'applied_rates', ['counter_group_id', 'counter_agency_id', 'counter_channel_id', 'counter_year'], unique=False)
    op.create_table('applied_rate_brackets',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('applied_rate_id', sa.BigInteger(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('lower', sa.Numeric(precision=24, scale=12), nullable=False),
    sa.Column('upper', sa.Numeric(precision=24, scale=12), nullable=True),
    sa.Column('rate', sa.Numeric(precision=20, scale=12), nullable=False),
    sa.Column('amount', sa.Numeric(precision=24, scale=12), nullable=False),
    sa.Column('rebate', sa.Numeric(precision=24, scale=12), nullable=False),
    sa.ForeignKeyConstraint(['applied_rate_id'], ['applied_rates.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('applied_rate_id', 'position', name='uq_applied_rate_brackets_rate_position')
    )

    # The system rate is data, not a constant in code: a later row at the system level supersedes it.
    op.execute("INSERT INTO platform_rate_settings (level, rate_per_thousand, created_by) VALUES ('system', 1.000000, NULL)")

    # Frozen rates are added once and never changed or deleted.
    op.execute("""
        CREATE FUNCTION reject_append_only_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
    """)
    for table in _APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_append_only_change()"
        )

    if created_extension:
        # Remembered on the extension itself, so the downgrade removes only what this migration created.
        op.execute(f"COMMENT ON EXTENSION btree_gist IS '{_EXTENSION_MARKER}'")


def downgrade() -> None:
    created_extension = op.get_bind().execute(
        sa.text(
            "SELECT coalesce(obj_description(oid, 'pg_extension') = :marker, false) "
            "FROM pg_extension WHERE extname = 'btree_gist'"
        ),
        {"marker": _EXTENSION_MARKER},
    ).scalar()
    for table in _APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.execute("DROP FUNCTION reject_append_only_change()")
    op.drop_table('applied_rate_brackets')
    op.drop_index('ix_applied_rates_counter', table_name='applied_rates')
    op.drop_table('applied_rates')
    op.drop_index('ix_platform_rate_settings_level', table_name='platform_rate_settings')
    op.drop_table('platform_rate_settings')
    op.drop_table('rebate_brackets')
    op.drop_table('rebate_schedules')
    if created_extension:
        op.execute("DROP EXTENSION btree_gist")
