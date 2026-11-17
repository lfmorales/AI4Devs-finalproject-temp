"""Through the real application: roles come from the database and a conflicting link answers 403."""

from dataclasses import replace

from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from app.application.services.authentication_service import AuthenticationService
from app.domain.models.user import RoleName, User
from app.infrastructure.auth.composite_token_verifier import CompositeTokenVerifier
from app.infrastructure.auth.issuer_token_verifier import IssuerTokenVerifier
from app.main import create_app
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import get_authentication_service
from tests.fixtures.identity import InMemoryUserRepository, build_user
from tests.fixtures.identity_tokens import (
    COGNITO,
    COGNITO_TEST_KEY,
    ENTRA,
    TEST_KEY,
    StaticKeys,
    bearer,
    cognito_token,
    entra_token,
)


def _client(users: list[User]) -> TestClient:
    router = APIRouter()

    @router.get("/probe/operations")
    def operations_probe(user: User = Depends(require_roles(RoleName.OPERATIONS))) -> dict[str, str]:
        return {"email": user.email}

    @router.get("/probe/finance")
    def finance_probe(user: User = Depends(require_roles(RoleName.FINANCE))) -> dict[str, str]:
        return {"email": user.email}

    app = create_app()
    app.include_router(router)
    service = AuthenticationService(
        token_verifier=CompositeTokenVerifier(
            {
                ENTRA.issuer: IssuerTokenVerifier(ENTRA, StaticKeys(TEST_KEY.public_key())),
                COGNITO.issuer: IssuerTokenVerifier(COGNITO, StaticKeys(COGNITO_TEST_KEY.public_key())),
            }
        ),
        user_repository=InMemoryUserRepository(users),
    )
    app.dependency_overrides[get_authentication_service] = lambda: service
    return TestClient(app)


def test_an_entra_token_claiming_finance_is_authorised_with_the_roles_stored_in_the_database() -> None:
    client = _client([build_user(email="ops@example.com", roles=[RoleName.OPERATIONS])])
    token = entra_token({"roles": ["finance"]})

    assert client.get("/probe/operations", headers=bearer(token)).status_code == 200
    forbidden = client.get("/probe/finance", headers=bearer(token))
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "missing_role"


def test_a_conflicting_link_answers_403_with_its_code() -> None:
    linked_elsewhere = replace(
        build_user(email="ops@example.com"), identity_issuer=ENTRA.issuer, identity_subject="otro-sujeto"
    )
    client = _client([linked_elsewhere])

    response = client.get("/probe/operations", headers=bearer(entra_token({"oid": "sujeto-de-prueba"})))

    assert response.status_code == 403
    assert response.json()["code"] == "identity_link_conflict"


def test_a_cognito_token_is_authorised_with_the_roles_stored_in_the_database() -> None:
    client = _client([build_user(email="ops@example.com", roles=[RoleName.OPERATIONS])])
    token = cognito_token({"custom:roles": "finance"})

    assert client.get("/probe/operations", headers=bearer(token)).status_code == 200
    assert client.get("/probe/finance", headers=bearer(token)).status_code == 403


def test_a_user_without_roles_is_forbidden_on_every_protected_route() -> None:
    client = _client([build_user(email="ops@example.com", roles=[])])
    token = entra_token({"roles": ["operations", "finance"]})

    for path in ("/probe/operations", "/probe/finance"):
        response = client.get(path, headers=bearer(token))
        assert response.status_code == 403
        assert response.json()["code"] == "missing_role"


def test_two_stored_roles_compose() -> None:
    client = _client([build_user(email="ops@example.com", roles=[RoleName.OPERATIONS, RoleName.FINANCE])])
    token = entra_token()

    assert client.get("/probe/operations", headers=bearer(token)).status_code == 200
    assert client.get("/probe/finance", headers=bearer(token)).status_code == 200
