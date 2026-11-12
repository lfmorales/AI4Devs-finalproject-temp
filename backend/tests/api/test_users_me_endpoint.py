"""GET /users/me through the real application: the caller's roles from the database, ordered, and nothing else."""

from collections.abc import Callable
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.application.services.authentication_service import AuthenticationService
from app.domain.models.user import RoleName, User
from app.infrastructure.auth.composite_token_verifier import CompositeTokenVerifier
from app.infrastructure.auth.issuer_token_verifier import IssuerTokenVerifier
from app.main import create_app
from app.presentation.dependencies.providers import get_authentication_service
from tests.api.test_identity_authentication_api import (
    COGNITO,
    COGNITO_KEY,
    ENTRA,
    ENTRA_KEY,
    _bearer,
    _cognito_token,
    _entra_token,
    _StaticKeys,
)
from tests.fixtures.identity import InMemoryUserRepository, build_user

PATH = "/users/me"
EMAIL = "ops@example.com"


def _client(user: User) -> TestClient:
    app = create_app()
    service = AuthenticationService(
        token_verifier=CompositeTokenVerifier(
            {
                ENTRA.issuer: IssuerTokenVerifier(ENTRA, _StaticKeys(ENTRA_KEY)),
                COGNITO.issuer: IssuerTokenVerifier(COGNITO, _StaticKeys(COGNITO_KEY)),
            }
        ),
        user_repository=InMemoryUserRepository([user]),
    )
    app.dependency_overrides[get_authentication_service] = lambda: service
    return TestClient(app)


@pytest.mark.parametrize("make_token", [_entra_token, _cognito_token], ids=["entra", "cognito"])
def test_a_user_with_two_roles_receives_both_ordered_by_name(make_token: Callable[..., str]) -> None:
    client = _client(build_user(email=EMAIL, roles=[RoleName.OPERATIONS, RoleName.FINANCE]))

    response = client.get(PATH, headers=_bearer(make_token()))

    assert response.status_code == 200
    assert response.json() == {"roles": ["finance", "operations"]}


@pytest.mark.parametrize("make_token", [_entra_token, _cognito_token], ids=["entra", "cognito"])
def test_a_user_with_one_role_receives_that_role(make_token: Callable[..., str]) -> None:
    client = _client(build_user(email=EMAIL, roles=[RoleName.TRADING]))

    response = client.get(PATH, headers=_bearer(make_token()))

    assert response.status_code == 200
    assert response.json() == {"roles": ["trading"]}


def test_a_user_with_the_four_roles_receives_them_ordered() -> None:
    every_role = [RoleName.TRADING, RoleName.OPERATIONS, RoleName.BUSINESS, RoleName.FINANCE]
    client = _client(build_user(email=EMAIL, roles=every_role))

    response = client.get(PATH, headers=_bearer(_entra_token()))

    assert response.json() == {"roles": ["business", "finance", "operations", "trading"]}


def test_the_roles_come_from_the_database_and_not_from_the_token() -> None:
    client = _client(build_user(email=EMAIL, roles=[RoleName.TRADING]))

    response = client.get(PATH, headers=_bearer(_entra_token(roles=["operations", "finance"])))

    assert response.json() == {"roles": ["trading"]}


def test_a_user_without_any_role_is_forbidden_with_a_body_of_code_and_message_only() -> None:
    client = _client(build_user(email=EMAIL, roles=[]))

    response = client.get(PATH, headers=_bearer(_entra_token()))

    assert response.status_code == 403
    assert response.json()["code"] == "missing_role"
    assert set(response.json()) == {"code", "message"}


def test_an_inactive_user_is_forbidden_even_with_a_valid_token() -> None:
    client = _client(build_user(email=EMAIL, roles=[RoleName.OPERATIONS], is_active=False))

    response = client.get(PATH, headers=_bearer(_entra_token()))

    assert response.status_code == 403
    assert response.json()["code"] == "user_inactive"


def test_a_request_without_a_token_is_unauthenticated() -> None:
    client = _client(build_user(email=EMAIL, roles=[RoleName.OPERATIONS]))

    response = client.get(PATH)

    assert response.status_code == 401
    assert set(response.json()) == {"code", "message"}


def test_no_response_carries_the_email_an_identifier_or_a_money_figure() -> None:
    linked = replace(
        build_user(email=EMAIL, roles=[RoleName.OPERATIONS]), identity_issuer=ENTRA.issuer, identity_subject="sujeto"
    )
    responses = [
        _client(linked).get(PATH, headers=_bearer(_entra_token(subject="sujeto"))),
        _client(build_user(email=EMAIL, roles=[])).get(PATH, headers=_bearer(_entra_token())),
        _client(build_user(email=EMAIL, is_active=False)).get(PATH, headers=_bearer(_entra_token())),
        _client(linked).get(PATH),
    ]

    for response in responses:
        text = response.text.lower()
        assert EMAIL not in text
        assert "sujeto" not in text and "full_name" not in text
        assert not any(word in text for word in ("revenue", "rebate", "margin", "cost", "price"))
    assert set(responses[0].json()) == {"roles"}
