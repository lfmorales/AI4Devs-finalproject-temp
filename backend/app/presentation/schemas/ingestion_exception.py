from datetime import date, datetime

from pydantic import BaseModel

from app.domain.entities.ingestion_exception import ExceptionStatus, ExceptionType


class IngestionExceptionResponse(BaseModel):
    """No media cost: it is stored with the retained delivery but restricted to finance, which this queue is not."""

    id: int
    exception_type: ExceptionType
    status: ExceptionStatus
    ingestion_batch_id: int
    dsp_id: int | None
    external_campaign_id: str | None
    external_line_item_id: str | None
    campaign_line_id: int | None
    campaign_period_id: int | None
    first_date: date | None
    last_date: date | None
    days: int
    impressions_total: int
    clicks_total: int
    resolved_at: datetime | None
    resolved_by: int | None
    note: str | None


class ResolveExceptionRequest(BaseModel):
    note: str | None = None


class LinkExceptionRequest(BaseModel):
    campaign_line_id: int


class LinkedMappingResponse(BaseModel):
    id: int
    campaign_line_id: int
    dsp_id: int
    external_campaign_id: str
    external_line_item_id: str
    # Always set: the exception proves the pair exists in the DSP, so no question is asked to it.
    validated_at: datetime


class LinkExceptionResponse(BaseModel):
    mapping: LinkedMappingResponse
    exception: IngestionExceptionResponse
