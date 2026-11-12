from typing import Annotated

from fastapi import APIRouter, Depends

from app.application.services.user_activation_service import UserActivationService
from app.domain.models.user import RoleName, User
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import get_user_activation_service
from app.presentation.schemas.user import ActivationRequest, ActivationResponse, OwnRolesResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/activation", response_model=ActivationResponse)
def set_user_active(
    body: ActivationRequest,
    actor: Annotated[User, Depends(require_roles(RoleName.OPERATIONS))],
    service: Annotated[UserActivationService, Depends(get_user_activation_service)],
) -> ActivationResponse:
    """Set a user active or inactive; it takes effect on that user's next request. Requires: operations role."""
    user = service.set_active(actor, body.email, body.active)
    return ActivationResponse(email=user.email, is_active=user.is_active)


@router.get("/me", response_model=OwnRolesResponse)
def read_own_roles(
    user: Annotated[
        User, Depends(require_roles(RoleName.OPERATIONS, RoleName.BUSINESS, RoleName.FINANCE, RoleName.TRADING))
    ],
) -> OwnRolesResponse:
    """The caller's roles, from the database and ordered by name, so the interface shows what they may use."""
    # The authentication dependency has already loaded the user with its roles: no further query.
    return OwnRolesResponse(roles=sorted(role.value for role in user.roles))
