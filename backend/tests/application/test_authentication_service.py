import pytest

from app.application.services.authentication_service import AuthenticationService
from app.domain.exceptions import (
    InactiveUserError,
    InvalidIdentityTokenError,
    MissingRoleError,
    UnregisteredUserError,
)
from app.domain.models.user import RoleName, VerifiedIdentity
from app.domain.services.identity_token_verifier import IdentityTokenVerifier
from tests.fixtures.identity import (
    FakeIdentityTokenVerifier,
    InMemoryUserRepository,
    build_user,
)


def _service_for(*users_and_tokens: tuple[str, str]) -> AuthenticationService:
    return AuthenticationService(
        token_verifier=FakeIdentityTokenVerifier(dict(users_and_tokens)),
        user_repository=InMemoryUserRepository(
            [build_user(email="ops@example.com"), build_user(email="gone@example.com", is_active=False)]
        ),
    )


def test_authenticate_returns_registered_user_matched_by_email() -> None:
    service = _service_for(("valid-token", "ops@example.com"))

    user = service.authenticate("valid-token")

    assert user.email == "ops@example.com"


def test_authenticate_matches_email_case_insensitively() -> None:
    service = _service_for(("valid-token", "OPS@Example.com"))

    user = service.authenticate("valid-token")

    assert user.email == "ops@example.com"


def test_authenticate_propagates_invalid_token() -> None:
    service = _service_for()

    with pytest.raises(InvalidIdentityTokenError):
        service.authenticate("forged-token")


def test_authenticate_rejects_valid_identity_without_local_user_and_does_not_provision_it() -> None:
    service = _service_for(("valid-token", "stranger@example.com"))

    with pytest.raises(UnregisteredUserError):
        service.authenticate("valid-token")


def test_authenticate_rejects_inactive_user() -> None:
    service = _service_for(("valid-token", "gone@example.com"))

    with pytest.raises(InactiveUserError):
        service.authenticate("valid-token")


def test_authorize_accepts_user_holding_any_of_the_accepted_roles() -> None:
    user = build_user(roles=[RoleName.BUSINESS, RoleName.FINANCE])

    AuthenticationService.authorize(user, accepted_roles=[RoleName.OPERATIONS, RoleName.FINANCE])


def test_authorize_rejects_user_without_any_accepted_role() -> None:
    user = build_user(roles=[RoleName.OPERATIONS])

    with pytest.raises(MissingRoleError):
        AuthenticationService.authorize(user, accepted_roles=[RoleName.FINANCE])


def test_authorize_rejects_empty_role_requirement_instead_of_treating_it_as_open() -> None:
    user = build_user(roles=[RoleName.OPERATIONS])

    with pytest.raises(ValueError):
        AuthenticationService.authorize(user, accepted_roles=[])


class _VerifierWithoutEmail(IdentityTokenVerifier):
    def verify(self, token: str) -> VerifiedIdentity:
        return VerifiedIdentity(issuer="https://emisor-de-prueba.example.com", subject="identificador-de-prueba", email=None)


def test_authenticate_rejects_an_identity_without_email_as_not_registered() -> None:
    service = AuthenticationService(
        token_verifier=_VerifierWithoutEmail(), user_repository=InMemoryUserRepository([build_user()])
    )

    with pytest.raises(UnregisteredUserError):
        service.authenticate("any-token")
