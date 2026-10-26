from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.application.services.margin_closing_service import MarginClosingService
from app.application.services.margin_masters_service import MarginMastersService
from app.application.services.margin_query_service import MarginQueryService
from app.domain.value_objects.platform_rate import NewPlatformRateSetting
from app.domain.value_objects.rebate import Bracket, NewRebateSchedule
from app.domain.models.user import RoleName, User
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import (
    get_margin_closing_service,
    get_margin_masters_service,
    get_margin_query_service,
)
from app.presentation.schemas.margin import (
    BracketResponse,
    ClosingRequest,
    ClosingResponse,
    MarginResponse,
    PlatformRateRequest,
    PlatformRateResponse,
    RebateScheduleRequest,
    RebateScheduleResponse,
)

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


@router.post("/rebate-schedules", response_model=RebateScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_rebate_schedule(
    body: RebateScheduleRequest,
    _user: Annotated[User, Depends(require_roles(RoleName.FINANCE))],
    service: Annotated[MarginMastersService, Depends(get_margin_masters_service)],
) -> RebateScheduleResponse:
    """Create a rebate schedule with its brackets. Requires: finance role."""
    brackets = tuple(Bracket(item.lower, item.upper, item.rate) for item in body.brackets)
    schedule_id = service.create_schedule(NewRebateSchedule(
        holding_group_id=body.holding_group_id, agency_id=body.agency_id, channel_id=body.channel_id,
        scope=body.scope, valid_from=body.valid_from, valid_to=body.valid_to, brackets=brackets,
    ))
    return RebateScheduleResponse(
        id=schedule_id, holding_group_id=body.holding_group_id, agency_id=body.agency_id, channel_id=body.channel_id,
        scope=body.scope, valid_from=body.valid_from, valid_to=body.valid_to,
        brackets=[BracketResponse(lower=b.lower, upper=b.upper, rate=b.rate) for b in brackets],
    )


@router.post("/platform-rates", response_model=PlatformRateResponse, status_code=status.HTTP_201_CREATED)
def set_platform_rate(
    body: PlatformRateRequest,
    user: Annotated[User, Depends(require_roles(RoleName.FINANCE))],
    service: Annotated[MarginMastersService, Depends(get_margin_masters_service)],
) -> PlatformRateResponse:
    """Set a platform rate at a level; the latest setting of a level and key is the one in force. Requires: finance."""
    setting = service.set_platform_rate(NewPlatformRateSetting(
        level=body.level, rate_per_thousand=body.rate_per_thousand, created_by=user.id,
        campaign_line_id=body.campaign_line_id, agency_id=body.agency_id, campaign_type_id=body.campaign_type_id,
    ))
    return PlatformRateResponse(
        id=setting.setting_id, level=setting.level, rate_per_thousand=setting.rate_per_thousand,
        campaign_line_id=setting.campaign_line_id, agency_id=setting.agency_id,
        campaign_type_id=setting.campaign_type_id, created_by=setting.created_by, created_at=setting.created_at,
    )
