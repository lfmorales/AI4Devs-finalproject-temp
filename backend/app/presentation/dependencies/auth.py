from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.services.authentication_service import AuthenticationService
from app.domain.exceptions import InvalidIdentityTokenError
from app.domain.models.user import RoleName, User
from app.presentation.dependencies.providers import get_authentication_service

# auto_error=False so a missing token goes through the same 401 body as an invalid one.
_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    authentication_service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> User:
    if credentials is None:
        raise InvalidIdentityTokenError("Missing bearer token")
    return authentication_service.authenticate(credentials.credentials)


def require_roles(*accepted_roles: RoleName) -> Callable[[User], User]:
    """Dependency that authorises a user holding any one of the accepted roles."""
    if not accepted_roles:
        # Fails when the router module is imported, not on the first request.
        raise ValueError("require_roles needs at least one role")

    def _require_accepted_role(user: Annotated[User, Depends(get_current_user)]) -> User:
        AuthenticationService.authorize(user, accepted_roles)
        return user

    # Readable by tooling that audits which roles each route requires, e.g. the route protection test.
    _require_accepted_role.accepted_roles = accepted_roles  # type: ignore[attr-defined]
    return _require_accepted_role
