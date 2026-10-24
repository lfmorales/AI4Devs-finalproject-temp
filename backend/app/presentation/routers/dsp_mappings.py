from typing import Annotated

from fastapi import APIRouter, Depends

from app.application.services.dsp_mapping_service import DspMappingService
from app.domain.models.user import RoleName, User
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import get_dsp_mapping_service
from app.presentation.schemas.dsp_mapping import DspMappingCreateRequest, DspMappingResponse

router = APIRouter(prefix="/campaign-lines", tags=["dsp-mappings"])


@router.post("/{campaign_line_id}/dsp-mappings", status_code=201, response_model=DspMappingResponse)
def create_dsp_mapping(
    campaign_line_id: int,
    request: DspMappingCreateRequest,
    _user: Annotated[User, Depends(require_roles(RoleName.OPERATIONS))],
    service: Annotated[DspMappingService, Depends(get_dsp_mapping_service)],
) -> DspMappingResponse:
    """Map a campaign line to a DSP identifier pair, checking the pair with the DSP.

    Requires: operations role. The mapping is created whether the pair is found, unknown or the DSP is
    unreachable; `validated_at` is set only for a found pair, and `validation` says which case it was.
    """
    result = service.create_mapping(campaign_line_id, request.external_campaign_id, request.external_line_item_id)
    mapping = result.mapping
    return DspMappingResponse(
        id=mapping.id,
        campaign_line_id=mapping.campaign_line_id,
        dsp_id=mapping.dsp_id,
        external_campaign_id=mapping.key.external_campaign_id,
        external_line_item_id=mapping.key.external_line_item_id,
        validated_at=mapping.validated_at,
        validation=result.check,
    )
