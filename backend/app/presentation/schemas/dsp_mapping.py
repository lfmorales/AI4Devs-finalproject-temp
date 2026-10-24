from datetime import datetime

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
