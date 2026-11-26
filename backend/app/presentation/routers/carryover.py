"""The carry-over of a flight, written by operations or trading.

Trading may call it, so nothing it answers is ever an amount, a billable flag or an adjustment. Until its task is
implemented, it answers 501 with a code and a message.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.domain.models.user import RoleName, User
from app.presentation.dependencies.auth import require_roles
from app.presentation.routers.billing import not_implemented

router = APIRouter(prefix="/flights", tags=["flights"])


@router.put("/{flight_id}/carryover")
def put_carryover(
    flight_id: int,
    _user: Annotated[User, Depends(require_roles(RoleName.OPERATIONS, RoleName.TRADING))],
) -> JSONResponse:
    """Carry undelivered volume of the previous flight of the line to this one. Requires: operations or trading
    role."""
    return not_implemented()
