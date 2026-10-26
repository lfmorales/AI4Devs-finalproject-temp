"""Maps domain exceptions to HTTP responses. The domain never knows about status codes."""

import logging
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
    VolumeTooSmallForFlightsError,
    UnsupportedCurrencyError,
    DuplicateCampaignNameError,
    DuplicateOrderReferenceError,
    IdentityProviderUnavailableError,
    InactiveUserError,
    InvalidIdentityTokenError,
    MissingRoleError,
    PreviousMonthOpenError,
    RebateRuleError,
    SystemPlatformRateMissingError,
    UnregisteredUserError,
)
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
    MissingRoleError: _ErrorMapping(403, "missing_role", "User lacks the required role"),
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


def _is_margin_route(request: Request) -> bool:
    """Whether the request is for a route under /margin, whatever prefix a proxy adds in front."""
    path = request.scope["path"]
    root_path = request.scope.get("root_path", "")
    if root_path and path.startswith(root_path):
        path = path[len(root_path):]
    return path == "/margin" or path.startswith("/margin/")


_HTTP_ERROR_CODES = {404: "not_found", 405: "method_not_allowed"}


async def _validation_error_handler(request: Request, error: Exception) -> JSONResponse:
    """Margin routes answer {"code","message"}; the older routes keep FastAPI's {"detail": ...}."""
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
    app.add_exception_handler(RebateRuleError, _rebate_rule_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(Exception, _generic_error_handler)
