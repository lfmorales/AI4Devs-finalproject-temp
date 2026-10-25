from typing import Annotated

from fastapi import APIRouter, Depends

from app.domain.models.user import RoleName, User
from app.domain.services.flight_planning import resolve_line_windows, split_volume_by_days
from app.domain.services.period_expansion import PeriodExpansionService
from app.presentation.dependencies.auth import require_roles
from app.presentation.schemas.flight_preview import FlightPreviewFlight, FlightPreviewRequest, FlightPreviewResponse

router = APIRouter(prefix="/flights", tags=["flights"])


@router.post("/preview", response_model=FlightPreviewResponse)
def preview_flights(
    request: FlightPreviewRequest,
    _user: Annotated[User, Depends(require_roles(RoleName.OPERATIONS))],
) -> FlightPreviewResponse:
    """Compute the flights a line would get, split by days, without storing anything.

    Requires: operations role. The same domain functions as the registration decide the dates and the split.
    """
    periods = PeriodExpansionService().expand(request.campaign_start_date, request.campaign_end_date)
    plan = resolve_line_windows(
        request.start_date, request.end_date, request.campaign_start_date, request.campaign_end_date, periods
    )
    volumes = split_volume_by_days(request.contracted_impressions, plan.windows)
    return FlightPreviewResponse(
        start_date=plan.start_date,
        end_date=plan.end_date,
        flights=[
            FlightPreviewFlight(
                period_year=window.period_year,
                period_month=window.period_month,
                flight_start=window.flight_start,
                flight_end=window.flight_end,
                contracted_impressions=volume,
            )
            for window, volume in zip(plan.windows, volumes)
        ],
    )
