"""The carry-over of a flight, written by operations or trading.

Trading may call it, so nothing it answers is ever an amount, a billable flag or an adjustment.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.application.services.author_names import AuthorNames
from app.application.services.carryover_service import CarryoverService
from app.domain.models.user import RoleName, User
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import get_author_names, get_carryover_service
from app.presentation.schemas.carryover import CarryoverRequest, CarryoverResponse

router = APIRouter(prefix="/flights", tags=["flights"])


@router.put("/{flight_id}/carryover", response_model=CarryoverResponse)
def put_carryover(
    body: CarryoverRequest,
    user: Annotated[User, Depends(require_roles(RoleName.OPERATIONS, RoleName.TRADING))],
    service: Annotated[CarryoverService, Depends(get_carryover_service)],
    names: Annotated[AuthorNames, Depends(get_author_names)],
    flight_id: Annotated[int, Path(ge=1)],
) -> CarryoverResponse:
    """Carry undelivered volume of the previous flight of the line to this one, with a mandatory reason. A volume of
    zero removes the carry-over. Requires: operations or trading role."""
    result = service.put_carryover(flight_id, body.volume, body.reason, user.id)
    return CarryoverResponse.from_result(result, names.of([result.set_by]))
