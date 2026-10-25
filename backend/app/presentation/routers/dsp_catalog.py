from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.application.services.dsp_catalog_service import DspCatalogService
from app.domain.entities.dsp_catalog import CatalogQuery
from app.domain.models.user import RoleName, User
from app.presentation.dependencies.auth import require_roles
from app.presentation.dependencies.providers import get_dsp_catalog_service
from app.presentation.schemas.dsp_catalog import DspCatalogItemResponse, DspCatalogPageResponse

router = APIRouter(prefix="/dsp-catalog", tags=["dsp-catalog"])

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50


@router.get("", response_model=DspCatalogPageResponse)
def list_dsp_catalog(
    _user: Annotated[User, Depends(require_roles(RoleName.OPERATIONS))],
    service: Annotated[DspCatalogService, Depends(get_dsp_catalog_service)],
    dsp_id: Annotated[int | None, Query()] = None,
    q: Annotated[str | None, Query(description="Text in the campaign or line item name, any case")] = None,
    mapped: Annotated[bool | None, Query(description="true: only mapped pairs; false: only unmapped ones")] = None,
    active_since: Annotated[date | None, Query(description="Keep pairs whose last_seen_date is on or after it")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DspCatalogPageResponse:
    """The Adform line items the ingestion has seen, to choose the pair a campaign line maps to.

    Requires: operations role. `last_seen_date` is the last date with a row in the DSP, not real activity.
    """
    page = service.search(CatalogQuery(dsp_id, q.strip() if q else None, mapped, active_since, limit, offset))
    return DspCatalogPageResponse(
        items=[DspCatalogItemResponse(**vars(item)) for item in page.items],
        total=page.total, limit=limit, offset=offset,
    )
