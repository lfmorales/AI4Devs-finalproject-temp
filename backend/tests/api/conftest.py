import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, selectinload

from app.main import create_app
from app.presentation.dependencies import providers, auth
from app.infrastructure.persistence.models.identity import UserRecord, RoleRecord, UserRoleRecord
from app.domain.models.user import User, RoleName
from app.domain.exceptions import UnregisteredUserError
from tests.fixtures.master_data import seed_master_data


@pytest.fixture
def client(test_db_session):
    """Provide a synchronous TestClient without authentication overrides."""
    app = create_app()

    # Override get_db_session to use the isolated test session
    def override_get_db_session():
        yield test_db_session

    app.dependency_overrides[providers.get_db_session] = override_get_db_session

    # Seed master data in the test session
    seed_master_data(test_db_session)

    yield TestClient(app)

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(test_db_session):
    """Provide TestClient with real user and roles loaded from database."""
    # Seed master data in this session
    seed_master_data(test_db_session)

    # Create test user
    user = UserRecord(email="api_test@example.com", full_name="API Test User", is_active=True)
    test_db_session.add(user)
    test_db_session.flush()  # flush instead of commit

    # Get operations role
    ops_role = test_db_session.query(RoleRecord).filter_by(name="operations").first()
    assert ops_role is not None, "Operations role not found after seeding"

    # Assign operations role to user
    user_role = UserRoleRecord(user_id=user.id, role_id=ops_role.id)
    test_db_session.add(user_role)
    test_db_session.flush()

    # Create app and override get_db_session
    app = create_app()

    def override_get_db_session():
        yield test_db_session

    def override_get_current_user() -> User:
        user_record = test_db_session.query(UserRecord).options(
            selectinload(UserRecord.roles)
        ).filter_by(email="api_test@example.com").first()

        if user_record is None:
            raise UnregisteredUserError("Test user not found")

        roles = frozenset(RoleName(role.name) for role in user_record.roles)

        return User(
            id=user_record.id,
            email=user_record.email,
            full_name=user_record.full_name,
            is_active=user_record.is_active,
            roles=roles,
        )

    # Apply overrides
    app.dependency_overrides[providers.get_db_session] = override_get_db_session
    app.dependency_overrides[auth.get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    # Clean up all overrides
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client_no_operations_role(test_db_session):
    """Provide TestClient with user who has finance role but not operations."""
    # Seed master data in this session
    seed_master_data(test_db_session)

    # Create test user
    user = UserRecord(email="api_test_finance@example.com", full_name="Finance Test User", is_active=True)
    test_db_session.add(user)
    test_db_session.flush()

    # Get finance role (not operations)
    finance_role = test_db_session.query(RoleRecord).filter_by(name="finance").first()
    assert finance_role is not None, "Finance role not found after seeding"

    # Assign finance role to user (not operations)
    user_role = UserRoleRecord(user_id=user.id, role_id=finance_role.id)
    test_db_session.add(user_role)
    test_db_session.flush()

    # Create app and override dependencies
    app = create_app()

    def override_get_db_session():
        yield test_db_session

    def override_get_current_user() -> User:
        user_record = test_db_session.query(UserRecord).options(
            selectinload(UserRecord.roles)
        ).filter_by(email="api_test_finance@example.com").first()

        if user_record is None:
            raise UnregisteredUserError("Test user not found")

        roles = frozenset(RoleName(role.name) for role in user_record.roles)

        return User(
            id=user_record.id,
            email=user_record.email,
            full_name=user_record.full_name,
            is_active=user_record.is_active,
            roles=roles,
        )

    # Apply overrides
    app.dependency_overrides[providers.get_db_session] = override_get_db_session
    app.dependency_overrides[auth.get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    # Clean up all overrides
    app.dependency_overrides.clear()


@pytest.fixture
def client_for_roles(test_db_session):
    """Factory: a TestClient whose authenticated user holds exactly the given roles. Empty means no role at all."""
    seed_master_data(test_db_session)
    created: list = []

    def build(*role_names: str) -> TestClient:
        email = f"roles_{'_'.join(role_names) or 'none'}@example.com"
        user = UserRecord(email=email, full_name="Role Test User", is_active=True)
        test_db_session.add(user)
        test_db_session.flush()
        for role_name in role_names:
            role = test_db_session.query(RoleRecord).filter_by(name=role_name).first()
            assert role is not None, f"Role {role_name} not found after seeding"
            test_db_session.add(UserRoleRecord(user_id=user.id, role_id=role.id))
        test_db_session.flush()
        app = create_app()

        def override_get_current_user() -> User:
            record = test_db_session.query(UserRecord).options(selectinload(UserRecord.roles)).filter_by(email=email).one()
            return User(
                id=record.id, email=record.email, full_name=record.full_name, is_active=record.is_active,
                roles=frozenset(RoleName(role.name) for role in record.roles),
            )

        app.dependency_overrides[providers.get_db_session] = lambda: (yield test_db_session)
        app.dependency_overrides[auth.get_current_user] = override_get_current_user
        created.append(app)
        return TestClient(app)

    yield build
    for app in created:
        app.dependency_overrides.clear()
