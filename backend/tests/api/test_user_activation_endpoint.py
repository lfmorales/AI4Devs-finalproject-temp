"""POST /users/activation through the real application, with the real authentication service and user repository."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.application.services.authentication_service import AuthenticationService
from app.application.services.user_activation_service import UserActivationService
from app.domain.models.user import RoleName
from app.infrastructure.persistence.models.identity import RoleRecord, UserRecord, UserRoleRecord
from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from app.main import create_app
from app.presentation.dependencies import providers
from tests.fixtures.identity import FakeIdentityTokenVerifier
from tests.fixtures.master_data import seed_master_data

PATH = "/users/activation"
EMAILS = {
    "operations": "ops-actor@example.com",
    "other-operations": "ops-other@example.com",
    "finance": "fin@example.com",
    "business": "biz@example.com",
    "trading": "trd@example.com",
    "target": "target@example.com",
}
TOKENS = {f"{name}-token": email for name, email in EMAILS.items()}


def _token(name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {name}-token"}


@pytest.fixture
def world(test_db_session: Session) -> TestClient:
    seed_master_data(test_db_session)
    roles = {
        "operations": [RoleName.OPERATIONS],
        "other-operations": [RoleName.OPERATIONS],
        "finance": [RoleName.FINANCE],
        "business": [RoleName.BUSINESS],
        "trading": [RoleName.TRADING],
        "target": [RoleName.FINANCE],
    }
    for name, held in roles.items():
        user = UserRecord(email=EMAILS[name], full_name=name, is_active=True)
        test_db_session.add(user)
        test_db_session.flush()
        for role in held:
            role_record = test_db_session.query(RoleRecord).filter_by(name=role.value).one()
            test_db_session.add(UserRoleRecord(user_id=user.id, role_id=role_record.id))
    test_db_session.commit()

    app = create_app()
    app.dependency_overrides[providers.get_db_session] = lambda: (yield test_db_session)
    app.dependency_overrides[providers.get_authentication_service] = lambda: AuthenticationService(
        FakeIdentityTokenVerifier(TOKENS), SqlAlchemyUserRepository(test_db_session)
    )
    return TestClient(app)


def _set(client: TestClient, caller: str, email: str, active: object) -> Response:
    response: Response = client.post(PATH, json={"email": email, "active": active}, headers=_token(caller))
    return response


def _is_active(session: Session, email: str) -> bool:
    session.expire_all()
    return session.query(UserRecord).filter_by(email=email).one().is_active


def test_operations_deactivates_a_user_whose_token_is_still_valid_and_the_next_request_is_forbidden(
    world: TestClient,
) -> None:
    assert world.get("/masters/agencies", headers=_token("target")).status_code == 200

    response = _set(world, "operations", EMAILS["target"], False)

    assert response.status_code == 200
    assert response.json() == {"email": EMAILS["target"], "is_active": False}
    forbidden = world.get("/masters/agencies", headers=_token("target"))
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "user_inactive"


def test_a_reactivated_user_gets_in_again_with_the_same_token(world: TestClient) -> None:
    _set(world, "operations", EMAILS["target"], False)

    response = _set(world, "operations", EMAILS["target"], True)

    assert response.status_code == 200
    assert response.json() == {"email": EMAILS["target"], "is_active": True}
    assert world.get("/masters/agencies", headers=_token("target")).status_code == 200


@pytest.mark.parametrize("caller", ["finance", "business", "trading"])
def test_a_user_without_operations_is_forbidden_and_nothing_changes(
    world: TestClient, test_db_session: Session, caller: str
) -> None:
    response = _set(world, caller, EMAILS["target"], False)

    assert response.status_code == 403
    assert set(response.json()) == {"code", "message"}
    assert _is_active(test_db_session, EMAILS["target"]) is True


def test_a_request_without_a_token_is_unauthenticated(world: TestClient, test_db_session: Session) -> None:
    response = world.post(PATH, json={"email": EMAILS["target"], "active": False})

    assert response.status_code == 401
    assert set(response.json()) == {"code", "message"}
    assert _is_active(test_db_session, EMAILS["target"]) is True


def test_an_email_that_matches_no_user_is_not_found_and_the_answer_does_not_echo_it(world: TestClient) -> None:
    response = _set(world, "operations", "nobody@example.com", False)

    assert response.status_code == 404
    assert response.json()["code"] == "user_not_found"
    assert set(response.json()) == {"code", "message"}
    assert "nobody" not in response.text


def test_operations_cannot_deactivate_itself(world: TestClient, test_db_session: Session) -> None:
    response = _set(world, "operations", EMAILS["operations"], False)

    assert response.status_code == 409
    assert response.json()["code"] == "cannot_deactivate_self"
    assert set(response.json()) == {"code", "message"}
    assert _is_active(test_db_session, EMAILS["operations"]) is True


def test_operations_can_reactivate_itself_without_complaint(world: TestClient) -> None:
    assert _set(world, "operations", EMAILS["operations"], True).status_code == 200


def test_operations_deactivates_another_operations_user_while_the_caller_remains_active(
    world: TestClient, test_db_session: Session
) -> None:
    response = _set(world, "operations", EMAILS["other-operations"], False)

    assert response.status_code == 200
    assert _is_active(test_db_session, EMAILS["other-operations"]) is False


class _GuardBlocksRepository(SqlAlchemyUserRepository):
    """The database guard reports that the target is the last active operations user."""

    def set_active(self, user_id: int, active: bool, *, keep_one_active_with_role: RoleName | None = None) -> bool:
        return False if keep_one_active_with_role is not None else super().set_active(user_id, active)


def test_the_last_active_operations_user_is_a_conflict_with_its_own_code(
    world: TestClient, test_db_session: Session
) -> None:
    """Reachable for real only when two operations users deactivate each other at once (see the concurrency test)."""
    app = world.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[providers.get_user_activation_service] = lambda: UserActivationService(
        _GuardBlocksRepository(test_db_session)
    )

    response = _set(world, "operations", EMAILS["other-operations"], False)

    assert response.status_code == 409
    assert response.json()["code"] == "last_active_operations_user"
    assert set(response.json()) == {"code", "message"}
    assert _is_active(test_db_session, EMAILS["other-operations"]) is True


@pytest.mark.parametrize("active", [False, True])
def test_setting_the_state_a_user_already_has_is_idempotent(world: TestClient, active: bool) -> None:
    _set(world, "operations", EMAILS["target"], active)

    again = _set(world, "operations", EMAILS["target"], active)

    assert again.status_code == 200
    assert again.json() == {"email": EMAILS["target"], "is_active": active}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"email": EMAILS["target"]},
        {"active": False},
        {"email": EMAILS["target"], "active": "yes"},
        {"email": EMAILS["target"], "active": 1},
        {"email": "", "active": False},
        {"email": EMAILS["target"], "active": False, "roles": ["operations"]},
    ],
)
def test_an_invalid_body_is_422_and_does_not_echo_what_was_sent(
    world: TestClient, test_db_session: Session, body: dict[str, object]
) -> None:
    response = world.post(PATH, json=body, headers=_token("operations"))

    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}
    assert EMAILS["target"] not in response.text
    assert _is_active(test_db_session, EMAILS["target"]) is True


def test_no_response_carries_roles_or_other_data_of_the_user(world: TestClient) -> None:
    success = _set(world, "operations", EMAILS["target"], False)
    missing = _set(world, "operations", "nobody@example.com", False)
    own = _set(world, "operations", EMAILS["operations"], False)

    assert set(success.json()) == {"email", "is_active"}
    assert set(missing.json()) == {"code", "message"}
    assert set(own.json()) == {"code", "message"}
    for response in (success, missing, own):
        assert "role" not in response.text.lower()
        assert "full_name" not in response.text
