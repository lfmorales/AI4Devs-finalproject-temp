from typing import Annotated

from fastapi import APIRouter, Depends

from app.application.services.campaign_line_service import CampaignLineService
from app.application.services.line_mapping_removal_service import LineMappingRemovalService
from app.domain.models.user import RoleName, User
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import get_campaign_line_service, get_line_mapping_removal_service
from app.presentation.schemas.campaign_line import UnlinkLineResponse, UnmappedLineResponse

router = APIRouter(prefix="/campaign-lines", tags=["campaign-lines"])


@router.get("/unmapped", response_model=list[UnmappedLineResponse])
def list_unmapped_campaign_lines(
    _user: Annotated[User, Depends(require_roles(RoleName.OPERATIONS))],
    service: Annotated[CampaignLineService, Depends(get_campaign_line_service)],
) -> list[UnmappedLineResponse]:
    """The campaign lines that have no DSP mapping yet. Requires: operations role."""
    return [UnmappedLineResponse(**vars(line)) for line in service.list_unmapped()]


@router.delete("/{campaign_line_id}/dsp-mappings", response_model=UnlinkLineResponse)
def delete_line_dsp_mapping(
    campaign_line_id: int,
    _user: Annotated[User, Depends(require_roles(RoleName.OPERATIONS))],
    service: Annotated[LineMappingRemovalService, Depends(get_line_mapping_removal_service)],
) -> UnlinkLineResponse:
    """Delete the line's only mapping together with the delivery ingested through it. Requires: operations role.

    Several mappings answer 409 and none 404. The exception is not reopened: the delivery reappears as unmatched
    at the next ingestion.
    """
    return UnlinkLineResponse(
        campaign_line_id=campaign_line_id, removed_delivery_days=service.unlink(campaign_line_id)
    )
