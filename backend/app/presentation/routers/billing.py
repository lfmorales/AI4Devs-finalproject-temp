"""The billing routes of committed-billing-and-review, guarded for operations and finance.

Each route declares its roles now, ahead of its behaviour, so that the access matrix holds from the start; until
its task is implemented, a route answers 501 with a code and a message and no figure.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status
from fastapi.responses import JSONResponse

from app.application.services.billing_adjustment_service import BillingAdjustmentService
from app.application.services.carryover_service import CarryoverService
from app.application.services.monthly_review_service import MonthlyReviewService
from app.domain.models.user import RoleName, User
from app.domain.value_objects.billing import BillingBasis
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import (
    get_billing_adjustment_service,
    get_carryover_service,
    get_monthly_review_service,
)
from app.presentation.schemas.billing_adjustments import (
    AdjustmentHistoryResponse,
    AdjustmentRequest,
    AdjustmentResponse,
)
from app.presentation.schemas.carryover import BillableRequest, BillableResponse
from app.presentation.schemas.monthly_review import ReviewRequest, ReviewResponse

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


@router.post("/flights/{flight_id}/adjustments", response_model=AdjustmentResponse, status_code=status.HTTP_201_CREATED)
def adjust_flight_billing(
    body: AdjustmentRequest,
    user: OperationsOrFinance,
    service: Annotated[BillingAdjustmentService, Depends(get_billing_adjustment_service)],
    flight_id: Annotated[int, Path(ge=1)],
) -> AdjustmentResponse:
    """Adjust the billing of an ended, unfrozen committed flight, with a mandatory reason. Adjustments are only added
    and the latest is in force. Requires: operations or finance role."""
    result = service.adjust(flight_id, BillingBasis(body.basis), body.amount, body.reason, user.id)
    return AdjustmentResponse.from_result(result)


@router.get("/flights/{flight_id}/adjustments", response_model=AdjustmentHistoryResponse)
def list_flight_adjustments(
    _user: OperationsOrFinance,
    service: Annotated[BillingAdjustmentService, Depends(get_billing_adjustment_service)],
    flight_id: Annotated[int, Path(ge=1)],
) -> AdjustmentHistoryResponse:
    """The adjustments of a flight, latest first, and which one is in force. Requires: operations or finance role."""
    return AdjustmentHistoryResponse.from_entries(service.history(flight_id))


@router.post("/reviews", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
def review_campaign_month(
    body: ReviewRequest,
    response: Response,
    user: OperationsOrFinance,
    service: Annotated[MonthlyReviewService, Depends(get_monthly_review_service)],
) -> ReviewResponse:
    """Mark a campaign reviewed in a month, once all its flights of the month have ended. A campaign already reviewed
    answers 200 with its current review and writes nothing. Requires: operations or finance role."""
    result = service.review(body.campaign_id, body.year, body.month, user.id)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return ReviewResponse.from_result(result)


@router.post("/reviews/withdrawals", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
def withdraw_campaign_month_review(
    body: ReviewRequest,
    user: OperationsOrFinance,
    service: Annotated[MonthlyReviewService, Depends(get_monthly_review_service)],
) -> ReviewResponse:
    """Withdraw the review of a campaign in a month: it goes back to pending review and the withdrawal stays in the
    history. Requires: operations or finance role."""
    return ReviewResponse.from_result(service.withdraw(body.campaign_id, body.year, body.month, user.id))


@router.put("/flights/{flight_id}/carryover/billable", response_model=BillableResponse)
def set_carryover_billable(
    body: BillableRequest,
    user: OperationsOrFinance,
    service: Annotated[CarryoverService, Depends(get_carryover_service)],
    flight_id: Annotated[int, Path(ge=1)],
) -> BillableResponse:
    """Decide whether a flight's carry-over is billable: true raises the cap of its billing to contracted plus
    carry-over. Does not change the volume. Requires: operations or finance role."""
    return BillableResponse.from_result(service.set_billable(flight_id, body.billable, user.id))


@router.get("/export")
def export_closed_month_billing(_user: OperationsOrFinance) -> JSONResponse:
    """The CSV of a closed month's billing. Requires: operations or finance role."""
    return not_implemented()
