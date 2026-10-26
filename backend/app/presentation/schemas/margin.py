from pydantic import BaseModel, Field


class ClosingRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class ClosingResponse(BaseModel):
    year: int
    month: int
    closed: int
    already_closed: int
