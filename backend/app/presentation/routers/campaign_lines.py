from typing import Annotated

from fastapi import APIRouter, Depends

from app.application.services.campaign_line_service import CampaignLineService
from app.domain.models.user import RoleName, User
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import get_campaign_line_service
from app.presentation.schemas.campaign_line import UnmappedLineResponse

router = APIRouter(prefix="/campaign-lines", tags=["campaign-lines"])


@router.get("/unmapped", response_model=list[UnmappedLineResponse])
def list_unmapped_campaign_lines(
    _user: Annotated[User, Depends(require_roles(RoleName.OPERATIONS))],
    service: Annotated[CampaignLineService, Depends(get_campaign_line_service)],
) -> list[UnmappedLineResponse]:
    """The campaign lines that have no DSP mapping yet. Requires: operations role."""
    return [UnmappedLineResponse(**vars(line)) for line in service.list_unmapped()]
