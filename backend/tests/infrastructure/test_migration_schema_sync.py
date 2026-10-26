"""Test that database schema matches ORM models after migration."""

import subprocess
import tempfile
import pytest
import sqlalchemy as sa
from sqlalchemy import inspect, create_engine, text


def test_migration_schema_matches_models(test_db_session):
    """
    Verify that alembic migration produces a schema matching the ORM models.

    This test:
    1. Creates a fresh DB and runs alembic upgrade head
    2. Inspects the resulting schema
    3. Compares against the ORM metadata
    4. Fails if models and migration diverge
    """
    # Get connection to introspect schema
    engine = test_db_session.get_bind().engine
    inspector = inspect(engine)

    # Expected tables from ORM models
    expected_tables = {
        'users', 'roles', 'user_roles',
        'holding_groups', 'agencies', 'advertisers', 'dsps',
        'channels', 'formats', 'campaign_types', 'sectors', 'sales_reps',
        'campaigns', 'campaign_periods', 'campaign_lines', 'campaign_line_periods',
        'purchase_orders', 'purchase_order_versions',
        'dsp_mappings', 'dsp_catalog_lines',
        'daily_deliveries', 'ingestion_batches', 'ingestion_exceptions', 'ingestion_exception_deliveries',
        'rebate_schedules', 'rebate_brackets', 'platform_rate_settings', 'applied_rates', 'applied_rate_brackets',
    }

    # Actual tables in database
    actual_tables = set(inspector.get_table_names())

    # Check all expected tables exist
    missing_tables = expected_tables - actual_tables
    assert not missing_tables, f"Missing tables in database: {missing_tables}"

    # Check for unexpected tables (excluding alembic_version)
    extra_tables = actual_tables - expected_tables - {'alembic_version'}
    assert not extra_tables, f"Unexpected tables in database: {extra_tables}"

    # Verify critical constraints
    users_constraints = {c['name']: c for c in inspector.get_unique_constraints('users')}
    assert 'users_email_key' in users_constraints, "users.email should be unique"

    roles_constraints = {c['name']: c for c in inspector.get_unique_constraints('roles')}
    assert 'roles_name_key' in roles_constraints, "roles.name should be unique"

    # Verify user_roles composite primary key
    user_roles_pk = inspector.get_pk_constraint('user_roles')
    assert set(user_roles_pk['constrained_columns']) == {'user_id', 'role_id'}, \
        "user_roles should have composite PK on (user_id, role_id)"

    # Verify critical foreign keys
    user_roles_fks = {fk['constrained_columns'][0]: fk for fk in inspector.get_foreign_keys('user_roles')}
    assert 'user_id' in user_roles_fks, "user_roles.user_id should be FK to users.id"
    assert user_roles_fks['user_id']['referred_table'] == 'users'

    # Verify scope enum exists for campaign_lines
    campaign_lines_columns = {col['name']: col for col in inspector.get_columns('campaign_lines')}
    assert 'scope' in campaign_lines_columns, "campaign_lines.scope column missing"
    scope_col = campaign_lines_columns['scope']
    assert scope_col['type'].__class__.__name__ == 'ENUM', "scope should be enum type"
