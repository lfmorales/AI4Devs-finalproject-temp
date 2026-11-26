"""The billing routes of committed-billing-and-review, guarded for operations and finance.

Each route declares its roles now, ahead of its behaviour, so that the access matrix holds from the start; until
its task is implemented, a route answers 501 with a code and a message and no figure.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.domain.models.user import RoleName, User
from app.presentation.dependencies.auth import require_roles

router = APIRouter(prefix="/billing", tags=["billing"])

OperationsOrFinance = Annotated[User, Depends(require_roles(RoleName.OPERATIONS, RoleName.FINANCE))]


def not_implemented() -> JSONResponse:
    """The body of a route whose behaviour is not implemented yet: a code and a message, never an amount."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"code": "not_implemented", "message": "This route is declared but not implemented yet."},
    )


@router.get("")
def get_billing(_user: OperationsOrFinance) -> JSONResponse:
    """The billing of a month per campaign, line and flight. Requires: operations or finance role."""
    return not_implemented()


@router.post("/flights/{flight_id}/adjustments")
def adjust_flight_billing(flight_id: int, _user: OperationsOrFinance) -> JSONResponse:
    """Adjust the billing of an ended, unfrozen committed flight. Requires: operations or finance role."""
    return not_implemented()


@router.get("/flights/{flight_id}/adjustments")
def list_flight_adjustments(flight_id: int, _user: OperationsOrFinance) -> JSONResponse:
    """The adjustments of a flight, latest first. Requires: operations or finance role."""
    return not_implemented()


@router.post("/reviews")
def review_campaign_month(_user: OperationsOrFinance) -> JSONResponse:
    """Mark a campaign reviewed in a month. Requires: operations or finance role."""
    return not_implemented()


@router.post("/reviews/withdrawals")
def withdraw_campaign_month_review(_user: OperationsOrFinance) -> JSONResponse:
    """Withdraw the review of a campaign in a month. Requires: operations or finance role."""
    return not_implemented()


@router.put("/flights/{flight_id}/carryover/billable")
def set_carryover_billable(flight_id: int, _user: OperationsOrFinance) -> JSONResponse:
    """Decide whether a flight's carry-over is billable. Requires: operations or finance role."""
    return not_implemented()


@router.get("/export")
def export_closed_month_billing(_user: OperationsOrFinance) -> JSONResponse:
    """The CSV of a closed month's billing. Requires: operations or finance role."""
    return not_implemented()
