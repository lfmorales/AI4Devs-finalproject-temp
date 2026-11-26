"""The billing routes of committed-billing-and-review, guarded for operations and finance: the read of a month, the
adjustments, the reviews, the billable flag of a carry-over and the CSV of a closed month."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.application.services.author_names import AuthorNames
from app.application.services.billing_adjustment_service import BillingAdjustmentService
from app.application.services.billing_export_service import BillingExportService
from app.application.services.billing_query_service import BillingQueryService
from app.application.services.carryover_service import CarryoverService
from app.application.services.monthly_review_service import MonthlyReviewService
from app.domain.models.user import RoleName, User
from app.domain.value_objects.billing import BillingBasis
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import (
    get_author_names,
    get_billing_adjustment_service,
    get_billing_export_service,
    get_billing_query_service,
    get_carryover_service,
    get_monthly_review_service,
)
from app.presentation.schemas.billing_adjustments import (
    AdjustmentHistoryResponse,
    AdjustmentRequest,
    AdjustmentResponse,
)
from app.presentation.schemas.billing_report import BillingResponse, report_authors
from app.presentation.schemas.carryover import BillableRequest, BillableResponse
from app.presentation.schemas.monthly_review import ReviewRequest, ReviewResponse

router = APIRouter(prefix="/billing", tags=["billing"])

OperationsOrFinance = Annotated[User, Depends(require_roles(RoleName.OPERATIONS, RoleName.FINANCE))]
Names = Annotated[AuthorNames, Depends(get_author_names)]


@router.get("", response_model=BillingResponse)
def get_billing(
    _user: OperationsOrFinance,
    service: Annotated[BillingQueryService, Depends(get_billing_query_service)],
    names: Names,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
    campaign_id: Annotated[int | None, Query(ge=1)] = None,
) -> BillingResponse:
    """The billing of a month per campaign, line and flight, with each campaign's review state. Its billing, billable
    volume and basis are `GET /margin`'s. Writes nothing. Requires: operations or finance role."""
    report = service.get_billing(year, month, campaign_id)
    return BillingResponse.from_report(report, names.of(report_authors(report)))


@router.post("/flights/{flight_id}/adjustments", response_model=AdjustmentResponse, status_code=status.HTTP_201_CREATED)
def adjust_flight_billing(
    body: AdjustmentRequest,
    user: OperationsOrFinance,
    service: Annotated[BillingAdjustmentService, Depends(get_billing_adjustment_service)],
    names: Names,
    flight_id: Annotated[int, Path(ge=1)],
) -> AdjustmentResponse:
    """Adjust the billing of an ended, unfrozen committed flight, with a mandatory reason. Adjustments are only added
    and the latest is in force. Requires: operations or finance role."""
    result = service.adjust(flight_id, BillingBasis(body.basis), body.amount, body.reason, user.id)
    return AdjustmentResponse.from_result(result, names.of([result.entry.created_by]))


@router.get("/flights/{flight_id}/adjustments", response_model=AdjustmentHistoryResponse)
def list_flight_adjustments(
    _user: OperationsOrFinance,
    service: Annotated[BillingAdjustmentService, Depends(get_billing_adjustment_service)],
    names: Names,
    flight_id: Annotated[int, Path(ge=1)],
) -> AdjustmentHistoryResponse:
    """The adjustments of a flight, latest first, and which one is in force. Requires: operations or finance role."""
    entries = service.history(flight_id)
    return AdjustmentHistoryResponse.from_entries(entries, names.of(entry.created_by for entry in entries))


@router.post("/reviews", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
def review_campaign_month(
    body: ReviewRequest,
    response: Response,
    user: OperationsOrFinance,
    service: Annotated[MonthlyReviewService, Depends(get_monthly_review_service)],
    names: Names,
) -> ReviewResponse:
    """Mark a campaign reviewed in a month, once all its flights of the month have ended. A campaign already reviewed
    answers 200 with its current review and writes nothing. Requires: operations or finance role."""
    result = service.review(body.campaign_id, body.year, body.month, user.id)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return ReviewResponse.from_result(result, names.of([result.set_by]))


@router.post("/reviews/withdrawals", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
def withdraw_campaign_month_review(
    body: ReviewRequest,
    user: OperationsOrFinance,
    service: Annotated[MonthlyReviewService, Depends(get_monthly_review_service)],
    names: Names,
) -> ReviewResponse:
    """Withdraw the review of a campaign in a month: it goes back to pending review and the withdrawal stays in the
    history. Requires: operations or finance role."""
    result = service.withdraw(body.campaign_id, body.year, body.month, user.id)
    return ReviewResponse.from_result(result, names.of([result.set_by]))


@router.put("/flights/{flight_id}/carryover/billable", response_model=BillableResponse)
def set_carryover_billable(
    body: BillableRequest,
    user: OperationsOrFinance,
    service: Annotated[CarryoverService, Depends(get_carryover_service)],
    names: Names,
    flight_id: Annotated[int, Path(ge=1)],
) -> BillableResponse:
    """Decide whether a flight's carry-over is billable: true raises the cap of its billing to contracted plus
    carry-over. Does not change the volume. Requires: operations or finance role."""
    result = service.set_billable(flight_id, body.billable, user.id)
    return BillableResponse.from_result(result, names.of([result.set_by]))


@router.get("/export", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def export_closed_month_billing(
    _user: OperationsOrFinance,
    service: Annotated[BillingExportService, Depends(get_billing_export_service)],
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> Response:
    """The CSV of a closed month's billing, `facturacion-YYYY-MM.csv`, built only from its closings' snapshots: UTF-8
    with a byte order mark, `;`, a decimal comma. A month not closed is 409 `month_not_closed`. Writes nothing.
    Requires: operations or finance role."""
    name, content = service.export(year, month)
    return Response(
        content=content, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
