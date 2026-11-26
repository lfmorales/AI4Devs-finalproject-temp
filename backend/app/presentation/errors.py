"""Maps domain exceptions to HTTP responses. The domain never knows about status codes."""

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

from app.domain.exceptions import (
    AmbiguousMappingError,
    CampaignNotFoundError,
    BillingAdjustmentError,
    CarryoverError,
    MonthlyReviewError,
    FlightNotFoundError,
    TargetLineNotAdjustableError,
    MappingNotFoundError,
    CampaignLineNotFoundError,
    DomainError,
    DspAuthenticationError,
    DspNotConfiguredError,
    DspNotSupportedError,
    DspReportFailedError,
    DspReportTimeoutError,
    DspResponseFormatError,
    DspUnreachableError,
    DuplicateDspMappingError,
    InvalidEquativPackageError,
    ExceptionNotLinkableError,
    LineDspMismatchError,
    LineNotFoundError,
    MappingPairTakenError,
    IngestionExceptionAlreadyResolvedError,
    FlightVolumeNotPositiveError,
    FlightVolumesIncompleteError,
    FlightVolumesMismatchError,
    IngestionExceptionNotFoundError,
    LineDatesInvalidError,
    LineDatesOutsideCampaignError,
    MixedDeliveryMetricsError,
    VolumeTooSmallForFlightsError,
    UnsupportedCurrencyError,
    DuplicateCampaignNameError,
    DuplicateOrderReferenceError,
    CannotDeactivateSelfError,
    IdentityConflictError,
    IdentityProviderUnavailableError,
    InactiveUserError,
    InvalidIdentityTokenError,
    LastActiveOperationsUserError,
    MissingRoleError,
    MonthDeliveryNotLoadedError,
    MonthNotClosedError,
    MonthNotReviewedError,
    PreviousMonthOpenError,
    RebateRuleError,
    SystemPlatformRateMissingError,
    UnregisteredUserError,
    UserNotFoundError,
)
from app.domain.value_objects.review import ReviewState
from app.presentation.schemas.errors import ErrorResponse


@dataclass(frozen=True)
class _ErrorMapping:
    status_code: int
    code: str
    message: str
    headers: dict[str, str] | None = None


# Messages are fixed rather than taken from the exception, so no internal detail leaks.
_ERROR_MAPPINGS: dict[type[DomainError], _ErrorMapping] = {
    InvalidIdentityTokenError: _ErrorMapping(
        401, "unauthenticated", "Missing or invalid credentials", {"WWW-Authenticate": "Bearer"}
    ),
    IdentityProviderUnavailableError: _ErrorMapping(
        503, "identity_provider_unavailable", "Credentials cannot be verified right now"
    ),
    UnregisteredUserError: _ErrorMapping(403, "user_not_registered", "User is not registered"),
    InactiveUserError: _ErrorMapping(403, "user_inactive", "User is inactive"),
    IdentityConflictError: _ErrorMapping(403, "identity_link_conflict", "Identity is linked to another account"),
    MissingRoleError: _ErrorMapping(403, "missing_role", "User lacks the required role"),
    UserNotFoundError: _ErrorMapping(404, "user_not_found", "The user does not exist"),
    CannotDeactivateSelfError: _ErrorMapping(409, "cannot_deactivate_self", "You cannot deactivate your own account"),
    LastActiveOperationsUserError: _ErrorMapping(
        409, "last_active_operations_user", "The last active operations user cannot be deactivated"
    ),
    DuplicateCampaignNameError: _ErrorMapping(
        409, "duplicate_campaign_name", "A campaign with this name already exists"
    ),
    DuplicateOrderReferenceError: _ErrorMapping(
        409, "duplicate_order_reference", "A purchase order with this reference already exists"
    ),
    DuplicateDspMappingError: _ErrorMapping(
        409, "duplicate_dsp_mapping", "These DSP identifiers are already mapped to a campaign line"
    ),
    IngestionExceptionNotFoundError: _ErrorMapping(404, "exception_not_found", "The exception does not exist"),
    IngestionExceptionAlreadyResolvedError: _ErrorMapping(
        409, "exception_already_resolved", "The exception is already resolved"
    ),
    ExceptionNotLinkableError: _ErrorMapping(
        409, "exception_not_linkable", "Only an unmatched-delivery exception can be linked to a line"
    ),
    MappingPairTakenError: _ErrorMapping(
        409, "mapping_pair_taken", "These DSP identifiers are already mapped to a campaign line"
    ),
    AmbiguousMappingError: _ErrorMapping(
        409, "ambiguous_mapping", "The campaign line has several mappings, so its delivery cannot be attributed to one"
    ),
    MappingNotFoundError: _ErrorMapping(404, "mapping_not_found", "The campaign line has no DSP mapping"),
    LineNotFoundError: _ErrorMapping(404, "line_not_found", "The campaign line does not exist"),
    LineDspMismatchError: _ErrorMapping(
        422, "line_dsp_mismatch", "The campaign line runs on a different DSP than the identifiers"
    ),
    LineDatesInvalidError: _ErrorMapping(
        422, "line_dates_invalid", "A line's start date cannot be after its end date"
    ),
    MixedDeliveryMetricsError: _ErrorMapping(
        422, "mixed_delivery_metrics", "A campaign cannot mix channels that count delivery in different metrics"
    ),
    VolumeTooSmallForFlightsError: _ErrorMapping(
        422, "volume_too_small_for_flights", "The line's volume is too small to give every flight impressions"
    ),
    LineDatesOutsideCampaignError: _ErrorMapping(
        422, "line_dates_outside_campaign", "A line's dates must fall within the campaign's dates"
    ),
    FlightVolumesIncompleteError: _ErrorMapping(
        422, "flight_volumes_incomplete", "The monthly volumes must cover exactly the months the line runs in"
    ),
    FlightVolumesMismatchError: _ErrorMapping(
        422, "flight_volumes_mismatch", "The monthly volumes must add up to the line's total"
    ),
    FlightVolumeNotPositiveError: _ErrorMapping(
        422, "flight_volume_not_positive", "Every monthly volume must be positive"
    ),
    CampaignLineNotFoundError: _ErrorMapping(404, "campaign_line_not_found", "The campaign line does not exist"),
    DspNotSupportedError: _ErrorMapping(
        422, "dsp_not_supported", "The campaign line's DSP has no connector yet"
    ),
    InvalidEquativPackageError: _ErrorMapping(
        422, "invalid_equativ_package",
        "An Equativ line is mapped by one auction package id, a whole number above zero with no leading zero, "
        "in both identifiers",
    ),
    DspNotConfiguredError: _ErrorMapping(503, "dsp_not_configured", "The DSP connector is not configured"),
    DspUnreachableError: _ErrorMapping(503, "dsp_unreachable", "The DSP cannot be reached right now"),
    # One public outcome for every way a DSP exchange can go wrong; the cause is logged, never returned.
    DspAuthenticationError: _ErrorMapping(502, "dsp_request_failed", "The DSP request failed"),
    DspReportFailedError: _ErrorMapping(502, "dsp_request_failed", "The DSP request failed"),
    DspReportTimeoutError: _ErrorMapping(502, "dsp_request_failed", "The DSP request failed"),
    DspResponseFormatError: _ErrorMapping(502, "dsp_request_failed", "The DSP request failed"),
    UnsupportedCurrencyError: _ErrorMapping(
        502, "dsp_response_unsupported", "The DSP reported data that cannot be processed"
    ),
    CampaignNotFoundError: _ErrorMapping(404, "campaign_not_found", "The campaign does not exist"),
    FlightNotFoundError: _ErrorMapping(404, "flight_not_found", "The flight does not exist"),
    TargetLineNotAdjustableError: _ErrorMapping(
        409, "target_line_not_adjustable", "A target line bills what its DSP reports: it cannot be adjusted"
    ),
    SystemPlatformRateMissingError: _ErrorMapping(
        500, "platform_rate_not_configured", "No system platform rate is configured"
    ),
}


def _handler_for(mapping: _ErrorMapping) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handle(request: Request, error: Exception) -> JSONResponse:
        if mapping.status_code >= 500:
            # The class names the cause for the operator; the message and traceback stay out of the log and the body.
            logger.warning("%s answered %s (%s)", type(error).__name__, mapping.status_code, mapping.code)
        body = ErrorResponse(code=mapping.code, message=mapping.message)
        return JSONResponse(
            status_code=mapping.status_code,
            content=body.model_dump(),
            headers=mapping.headers,
        )

    return handle


async def _generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle uncontrolled exceptions without exposing SQL or internal details."""
    logger.exception("Unhandled exception", exc_info=exc)
    body = ErrorResponse(code="internal_error", message="An unexpected error occurred")
    return JSONResponse(status_code=500, content=body.model_dump())


async def _previous_month_open_handler(request: Request, error: Exception) -> JSONResponse:
    """The one message that names a value: the month that blocks the closing, which is not sensitive."""
    assert isinstance(error, PreviousMonthOpenError)
    body = ErrorResponse(
        code="previous_month_open",
        message=f"An earlier month is still open: {error.year}-{error.month:02d}. Close it first.",
    )
    return JSONResponse(status_code=409, content=body.model_dump())


async def _month_delivery_not_loaded_handler(request: Request, error: Exception) -> JSONResponse:
    """Names the month and the DSP that block the closing; neither is sensitive."""
    assert isinstance(error, MonthDeliveryNotLoadedError)
    body = ErrorResponse(
        code="month_delivery_not_loaded",
        message=(
            f"The delivery of {error.year}-{error.month:02d} from {error.dsp_name} is not loaded up to its last day. "
            f"Load it, then {error.next_step}."
        ),
    )
    return JSONResponse(status_code=409, content=body.model_dump())


async def _month_not_closed_handler(request: Request, error: Exception) -> JSONResponse:
    """Names the month, which is not sensitive."""
    assert isinstance(error, MonthNotClosedError)
    body = ErrorResponse(
        code="month_not_closed",
        message=f"{error.year}-{error.month:02d} is not closed: its billing has no CSV until it is.",
    )
    return JSONResponse(status_code=409, content=body.model_dump())


_REVIEW_STATE_LABELS = {ReviewState.IN_PROGRESS: "in progress", ReviewState.PENDING_REVIEW: "pending review"}


async def _month_not_reviewed_handler(request: Request, error: Exception) -> JSONResponse:
    """Names the month and each campaign that blocks the closing with its state: a name and a state, never a figure."""
    assert isinstance(error, MonthNotReviewedError)
    listed = "; ".join(f"{name} ({_REVIEW_STATE_LABELS[state]})" for name, state in error.campaigns)
    body = ErrorResponse(
        code="month_not_reviewed",
        message=f"{error.year}-{error.month:02d} has campaigns not reviewed: {listed}. Review them, then close the month.",
    )
    return JSONResponse(status_code=409, content=body.model_dump())



# Each carry-over rule has its own status and code. The message is fixed, except the shortfall, which is the volume the
# user needs to try again and carries no amount of money.
_CARRYOVER_ERRORS: dict[str, tuple[int, str]] = {
    "invalid_carryover": (422, "A carry-over needs a whole volume of zero or more and a reason"),
    "no_previous_flight": (409, "The first flight of a line has no previous flight to carry from"),
    "previous_flight_not_ended": (409, "The previous flight of the line has not ended yet"),
    "carryover_exceeds_shortfall": (409, "The carry-over is above what the previous flight fell short"),
    "month_closed": (409, "The month of the flight is closed"),
    "no_carryover": (409, "The flight has no carry-over to bill"),
}


async def _carryover_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, CarryoverError)
    status_code, message = _CARRYOVER_ERRORS.get(error.code, (422, "A carry-over rule was broken"))
    if error.code == "carryover_exceeds_shortfall":
        message = str(error)
    return JSONResponse(status_code=status_code, content=ErrorResponse(code=error.code, message=message).model_dump())


_BILLING_ADJUSTMENT_ERRORS: dict[str, tuple[int, str]] = {
    "invalid_adjustment": (
        422, "An adjustment needs a reason, and an amount of zero or more, with two decimals at most, only with the custom basis"
    ),
    "flight_not_ended": (409, "Only a flight that has ended can be adjusted"),
    "flight_closed": (409, "A flight frozen by a closing cannot be adjusted"),
}


async def _billing_adjustment_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, BillingAdjustmentError)
    status_code, message = _BILLING_ADJUSTMENT_ERRORS.get(error.code, (422, "A billing adjustment rule was broken"))
    return JSONResponse(status_code=status_code, content=ErrorResponse(code=error.code, message=message).model_dump())


_MONTHLY_REVIEW_ERRORS: dict[str, tuple[int, str]] = {
    "campaign_month_not_found": (404, "The campaign has no flights in that month"),
    "campaign_month_in_progress": (409, "A flight of the campaign has not ended yet, so it cannot be reviewed"),
    "campaign_month_closed": (409, "The month of the campaign is closed"),
    "not_reviewed": (409, "The campaign is not reviewed in that month"),
}


async def _monthly_review_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, MonthlyReviewError)
    status_code, message = _MONTHLY_REVIEW_ERRORS.get(error.code, (409, "A review rule was broken"))
    return JSONResponse(status_code=status_code, content=ErrorResponse(code=error.code, message=message).model_dump())


# Each rebate rule has its own status and message; the message never carries the detail of the failure.
_REBATE_RULE_ERRORS: dict[str, tuple[int, str]] = {
    "bracket_table_empty": (422, "A bracket table needs at least one bracket"),
    "bracket_table_must_start_at_zero": (422, "The first bracket of a table must start at 0"),
    "bracket_table_not_contiguous": (422, "Each bracket must begin exactly where the previous one ends"),
    "last_bracket_must_be_open": (422, "The last bracket of a table must have no upper threshold"),
    "overlapping_schedules": (409, "More than one schedule matches the flight at the same step on its start date"),
    "schedule_overlaps_existing": (409, "Another schedule with the same key is in force during part of this validity"),
    "reference_not_found": (422, "The group, agency or channel of the request does not exist"),
    "revenue_must_not_be_negative": (422, "Revenue and counter positions must not be negative"),
    "duplicate_flight_id": (422, "A flight appears more than once in the request"),
    "validity_ends_before_it_starts": (422, "A schedule cannot end before it starts"),
}


async def _rebate_rule_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RebateRuleError)
    status_code, message = _REBATE_RULE_ERRORS.get(error.code, (422, "A rebate rule was broken"))
    return JSONResponse(status_code=status_code, content=ErrorResponse(code=error.code, message=message).model_dump())


# Routes whose validation and routing errors answer {"code","message"}. For /users it also keeps the body the caller
# sent, which holds an email, out of the response: FastAPI's default 422 would echo it.
_FIXED_BODY_ROUTE_PREFIXES = ("/margin", "/users", "/billing")
# The carry-over of a flight lives under /flights, whose other route (the preview) keeps FastAPI's body.
_FIXED_BODY_ROUTE_PATTERN = re.compile(r"^/flights/[^/]+/carryover$")


def _is_margin_route(request: Request) -> bool:
    """Whether the request is for a route under /margin or /users, whatever prefix a proxy adds in front."""
    path = request.scope["path"]
    root_path = request.scope.get("root_path", "")
    if root_path and path.startswith(root_path):
        path = path[len(root_path):]
    return bool(_FIXED_BODY_ROUTE_PATTERN.match(path)) or any(
        path == prefix or path.startswith(prefix + "/") for prefix in _FIXED_BODY_ROUTE_PREFIXES
    )


_HTTP_ERROR_CODES = {404: "not_found", 405: "method_not_allowed"}


async def _validation_error_handler(request: Request, error: Exception) -> JSONResponse:
    """Margin and user routes answer {"code","message"}; the older routes keep FastAPI's {"detail": ...}."""
    assert isinstance(error, RequestValidationError)
    if not _is_margin_route(request):
        return await request_validation_exception_handler(request, error)
    fields = sorted({".".join(str(part) for part in item["loc"][1:]) or str(item["loc"][0]) for item in error.errors()})
    body = ErrorResponse(code="validation_error", message=f"The request is not valid: {', '.join(fields)}")
    return JSONResponse(status_code=422, content=body.model_dump())


async def _http_error_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StarletteHTTPException)
    if not _is_margin_route(request):
        return await http_exception_handler(request, error)
    code = _HTTP_ERROR_CODES.get(error.status_code, "http_error")
    body = ErrorResponse(code=code, message="The request cannot be served")
    return JSONResponse(status_code=error.status_code, content=body.model_dump(), headers=error.headers)


def register_exception_handlers(app: FastAPI) -> None:
    for exception_type, mapping in _ERROR_MAPPINGS.items():
        app.add_exception_handler(exception_type, _handler_for(mapping))
    app.add_exception_handler(PreviousMonthOpenError, _previous_month_open_handler)
    app.add_exception_handler(MonthDeliveryNotLoadedError, _month_delivery_not_loaded_handler)
    app.add_exception_handler(MonthNotReviewedError, _month_not_reviewed_handler)
    app.add_exception_handler(MonthNotClosedError, _month_not_closed_handler)
    app.add_exception_handler(RebateRuleError, _rebate_rule_handler)
    app.add_exception_handler(CarryoverError, _carryover_handler)
    app.add_exception_handler(BillingAdjustmentError, _billing_adjustment_handler)
    app.add_exception_handler(MonthlyReviewError, _monthly_review_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(Exception, _generic_error_handler)
