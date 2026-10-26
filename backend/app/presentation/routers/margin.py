from typing import Annotated

from fastapi import APIRouter, Depends

from app.application.services.margin_closing_service import MarginClosingService
from app.domain.models.user import RoleName, User
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import get_margin_closing_service
from app.presentation.schemas.margin import ClosingRequest, ClosingResponse

router = APIRouter(prefix="/margin", tags=["margin"])


@router.post("/closings", response_model=ClosingResponse)
def close_month(
    body: ClosingRequest,
    user: Annotated[User, Depends(require_roles(RoleName.FINANCE))],
    service: Annotated[MarginClosingService, Depends(get_margin_closing_service)],
) -> ClosingResponse:
    """Freeze the rates of the flights that ended in a month. Idempotent. Requires: finance role."""
    result = service.close_month(body.year, body.month, closed_by=user.id)
    return ClosingResponse(year=result.year, month=result.month, closed=result.closed, already_closed=result.already_closed)
