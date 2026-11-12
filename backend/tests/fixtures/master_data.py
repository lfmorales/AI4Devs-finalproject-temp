"""SQL fixtures for master data in integration tests."""

from sqlalchemy.orm import Session
from sqlalchemy import text


def seed_master_data(session: Session):
    """Populate database with test master data (no test user).

    Tests that need a user should create one with a unique email to avoid
    conflicts when multiple tests run in sequence with per-test rollback.
    """

    # Reset sequences to ensure consistent IDs across tests
    # This is needed because sequences continue incrementing even when transactions rollback
    # The migrations insert the trading role, so the roles sequence restarts after the rows that exist.
    session.execute(text("SELECT setval('roles_id_seq', COALESCE((SELECT max(id) FROM roles), 0) + 1, false)"))
    session.execute(text("ALTER SEQUENCE holding_groups_id_seq RESTART WITH 1"))
    session.execute(text("ALTER SEQUENCE agencies_id_seq RESTART WITH 1"))
    session.execute(text("ALTER SEQUENCE advertisers_id_seq RESTART WITH 1"))
    session.execute(text("ALTER SEQUENCE dsps_id_seq RESTART WITH 1"))
    session.execute(text("ALTER SEQUENCE channels_id_seq RESTART WITH 1"))
    session.execute(text("ALTER SEQUENCE formats_id_seq RESTART WITH 1"))
    session.execute(text("ALTER SEQUENCE campaign_types_id_seq RESTART WITH 1"))
    session.execute(text("ALTER SEQUENCE sectors_id_seq RESTART WITH 1"))
    session.execute(text("ALTER SEQUENCE sales_reps_id_seq RESTART WITH 1"))

    # Ensure roles exist first (no FK dependencies)
    session.execute(text("""
        INSERT INTO roles (name) VALUES
        ('operations'),
        ('business'),
        ('finance'),
        ('trading')
        ON CONFLICT (name) DO NOTHING
    """))

    # Master data
    session.execute(text("""
        INSERT INTO holding_groups (name) VALUES
        ('Group A'), ('Group B')
        ON CONFLICT (name) DO NOTHING
    """))

    session.execute(text("""
        INSERT INTO agencies (holding_group_id, name) VALUES
        (1, 'Agency One'),
        (1, 'Agency Two'),
        (2, 'Agency Three')
        ON CONFLICT (name) DO NOTHING
    """))

    session.execute(text("""
        INSERT INTO advertisers (name) VALUES
        ('Advertiser One'),
        ('Advertiser Two')
        ON CONFLICT (name) DO NOTHING
    """))

    session.execute(text("""
        INSERT INTO dsps (name, is_active) VALUES
        ('Adform', true),
        ('Equativ', true),
        ('Displayce', false)
        ON CONFLICT (name) DO NOTHING
    """))

    session.execute(text("""
        INSERT INTO channels (name) VALUES
        ('Digital'),
        ('OOH'),
        ('DOOH')
        ON CONFLICT (name) DO NOTHING
    """))

    session.execute(text("""
        INSERT INTO formats (name) VALUES
        ('Banner'),
        ('Native'),
        ('Video')
        ON CONFLICT (name) DO NOTHING
    """))

    session.execute(text("""
        INSERT INTO campaign_types (name) VALUES
        ('Brand'),
        ('Performance'),
        ('Awareness')
        ON CONFLICT (name) DO NOTHING
    """))

    session.execute(text("""
        INSERT INTO sectors (name) VALUES
        ('Tech'),
        ('Finance'),
        ('Retail')
        ON CONFLICT (name) DO NOTHING
    """))

    session.execute(text("""
        INSERT INTO sales_reps (name) VALUES
        ('Rep One'),
        ('Rep Two')
        ON CONFLICT (name) DO NOTHING
    """))

    session.commit()


def cleanup_master_data(session: Session):
    """Clean up test data."""
    session.execute(text("DELETE FROM campaign_lines"))
    session.execute(text("DELETE FROM campaign_periods"))
    session.execute(text("DELETE FROM campaigns"))
    session.execute(text("DELETE FROM dsp_mappings"))
    session.execute(text("DELETE FROM purchase_order_versions"))
    session.execute(text("DELETE FROM purchase_orders"))
    session.commit()
