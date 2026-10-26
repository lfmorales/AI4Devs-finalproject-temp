from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.application.services.margin_closing_service import MarginClosingService
from app.application.services.margin_query_service import MarginQueryService
from app.domain.models.user import RoleName, User
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import get_margin_closing_service, get_margin_query_service
from app.presentation.schemas.margin import ClosingRequest, ClosingResponse, MarginResponse

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


@router.get("", response_model=MarginResponse)
def get_margin(
    _user: Annotated[User, Depends(require_roles(RoleName.FINANCE))],
    service: Annotated[MarginQueryService, Depends(get_margin_query_service)],
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    campaign_id: Annotated[int | None, Query(ge=1)] = None,
) -> MarginResponse:
    """The margin per campaign, line and flight. Writes nothing. Requires: finance role."""
    return MarginResponse.from_report(service.get_margin(year, month, campaign_id))
