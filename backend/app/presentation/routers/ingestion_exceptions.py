from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.application.services.exception_linking_service import ExceptionLinkingService
from app.application.services.ingestion_exception_service import IngestionExceptionService
from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionSummary
from app.domain.models.user import RoleName, User
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import get_exception_linking_service, get_ingestion_exception_service
from app.presentation.schemas.ingestion_exception import (
    IngestionExceptionResponse,
    LinkedMappingResponse,
    LinkExceptionRequest,
    LinkExceptionResponse,
    ResolveExceptionRequest,
)

router = APIRouter(prefix="/ingestion-exceptions", tags=["ingestion-exceptions"])


def _to_response(summary: ExceptionSummary) -> IngestionExceptionResponse:
    return IngestionExceptionResponse(
        id=summary.id,
        exception_type=summary.exception_type,
        status=summary.status,
        ingestion_batch_id=summary.ingestion_batch_id,
        dsp_id=summary.dsp_id,
        external_campaign_id=summary.external_campaign_id,
        external_line_item_id=summary.external_line_item_id,
        campaign_line_id=summary.campaign_line_id,
        campaign_period_id=summary.campaign_period_id,
        first_date=summary.first_date,
        last_date=summary.last_date,
        days=summary.days,
        impressions_total=summary.impressions_total,
        clicks_total=summary.clicks_total,
        resolved_at=summary.resolved_at,
        resolved_by=summary.resolved_by,
        note=summary.note,
    )


@router.get("", response_model=list[IngestionExceptionResponse])
def list_ingestion_exceptions(
    _user: Annotated[User, Depends(require_roles(RoleName.OPERATIONS))],
    service: Annotated[IngestionExceptionService, Depends(get_ingestion_exception_service)],
    status: Annotated[ExceptionStatus | None, Query()] = None,
) -> list[IngestionExceptionResponse]:
    """The exception queue, optionally filtered by status. Requires: operations role."""
    return [_to_response(summary) for summary in service.list_exceptions(status)]


@router.post("/{exception_id}/resolve", response_model=IngestionExceptionResponse)
def resolve_ingestion_exception(
    exception_id: int,
    user: Annotated[User, Depends(require_roles(RoleName.OPERATIONS))],
    service: Annotated[IngestionExceptionService, Depends(get_ingestion_exception_service)],
    request: ResolveExceptionRequest | None = None,
) -> IngestionExceptionResponse:
    """Mark an exception resolved, with an optional note. It only marks: nothing is reprocessed. Requires: operations."""
    note = request.note if request is not None else None
    return _to_response(service.resolve(exception_id, user.id, note))


@router.post("/{exception_id}/link", response_model=LinkExceptionResponse)
def link_ingestion_exception(
    exception_id: int,
    request: LinkExceptionRequest,
    user: Annotated[User, Depends(require_roles(RoleName.OPERATIONS))],
    service: Annotated[ExceptionLinkingService, Depends(get_exception_linking_service)],
) -> LinkExceptionResponse:
    """Map the pair of an unmatched-delivery exception to a campaign line and resolve the exception, as one change.

    Requires: operations role. The mapping is validated without asking the DSP, because the exception proves the
    pair exists there. The retained delivery is not moved: the next ingestion window brings it in.
    """
    result = service.link(exception_id, request.campaign_line_id, user.id)
    mapping = result.mapping
    assert mapping.validated_at is not None
    return LinkExceptionResponse(
        mapping=LinkedMappingResponse(
            id=mapping.id, campaign_line_id=mapping.campaign_line_id, dsp_id=mapping.dsp_id,
            external_campaign_id=mapping.key.external_campaign_id, external_line_item_id=mapping.key.external_line_item_id,
            validated_at=mapping.validated_at,
        ),
        exception=_to_response(result.exception),
    )
