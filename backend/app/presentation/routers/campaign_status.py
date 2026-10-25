from typing import Annotated

from fastapi import APIRouter, Depends

from app.application.services.campaign_status_service import CampaignStatusService
from app.domain.models.user import RoleName, User
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import get_campaign_status_service
from app.presentation.schemas.campaign_status import CampaignStatusResponse

router = APIRouter(prefix="/campaign-status", tags=["campaign-status"])


@router.get("", response_model=list[CampaignStatusResponse])
def list_campaign_status(
    _user: Annotated[User, Depends(require_roles(RoleName.OPERATIONS, RoleName.BUSINESS))],
    service: Annotated[CampaignStatusService, Depends(get_campaign_status_service)],
) -> list[CampaignStatusResponse]:
    """The daily status: one row per running flight of an active campaign. Requires: operations or business role."""
    return [CampaignStatusResponse.from_row(row) for row in service.list_status()]
