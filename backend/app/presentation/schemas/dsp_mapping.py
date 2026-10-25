from datetime import date, datetime

from pydantic import BaseModel, Field

from app.application.services.dsp_mapping_service import IdentifierCheck


class DspMappingCreateRequest(BaseModel):
    external_campaign_id: str = Field(min_length=1)
    external_line_item_id: str = Field(min_length=1)


class DspMappingResponse(BaseModel):
    id: int
    campaign_line_id: int
    dsp_id: int
    external_campaign_id: str
    external_line_item_id: str
    validated_at: datetime | None
    validation: IdentifierCheck
    # New and optional: when the pair is in the catalogue, the latest date it delivered impressions. A pair that
    # exists but never delivers shows null here while `validation` may still say found.
    last_impressions_date: date | None = None
    # True when the line started before the normal ingestion window: the delivery before it is not loaded by itself.
    needs_history_load: bool = False
