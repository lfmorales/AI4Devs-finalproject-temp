"""Maps domain exceptions to HTTP responses. The domain never knows about status codes."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from app.domain.exceptions import (
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
    IngestionExceptionAlreadyResolvedError,
    IngestionExceptionNotFoundError,
    LineDatesOutsideCampaignError,
    UnsupportedCurrencyError,
    DuplicateCampaignNameError,
    DuplicateOrderReferenceError,
    IdentityProviderUnavailableError,
    InactiveUserError,
    InvalidIdentityTokenError,
    MissingRoleError,
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
    LineDatesOutsideCampaignError: _ErrorMapping(
        422, "line_dates_outside_campaign", "A line's dates must fall within the campaign's dates"
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


def register_exception_handlers(app: FastAPI) -> None:
    for exception_type, mapping in _ERROR_MAPPINGS.items():
        app.add_exception_handler(exception_type, _handler_for(mapping))
    app.add_exception_handler(Exception, _generic_error_handler)
