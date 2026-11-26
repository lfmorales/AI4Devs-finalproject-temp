from datetime import datetime

from pydantic import BaseModel, Field, StrictBool, StrictInt

from app.application.services.carryover_service import BillableResult, CarryoverResult
from app.presentation.schemas.quantity import IN_DELIVERY_METRIC


class CarryoverRequest(BaseModel):
    volume: StrictInt = Field(
        description=f"The volume carried to the flight, a whole number, {IN_DELIVERY_METRIC}; 0 removes the carry-over."
    )
    reason: str = Field(description="Why it is carried. Mandatory: an empty or blank reason is refused.")


class CarryoverResponse(BaseModel):
    """The carry-over of a flight. Open to trading: volumes and the reason only, never an amount or a billable flag."""

    flight_id: int
    delivery_metric: str = Field(description="The unit the channel counts delivery in: `impressions` or `ots`.")
    contracted_impressions: int = Field(description=f"The flight's contracted volume, {IN_DELIVERY_METRIC}. Unchanged.")
    carryover: int = Field(description=f"The volume carried to the flight, {IN_DELIVERY_METRIC}.")
    delivery_target: int = Field(description=f"The contracted volume plus the carry-over, {IN_DELIVERY_METRIC}.")
    reason: str
    set_by: int = Field(description="The user who wrote it.")
    set_at: datetime = Field(description="When it was written.")

    @classmethod
    def from_result(cls, result: CarryoverResult) -> "CarryoverResponse":
        return cls(
            flight_id=result.flight_id, delivery_metric=result.delivery_metric,
            contracted_impressions=result.contracted_impressions, carryover=result.carryover,
            delivery_target=result.delivery_target, reason=result.reason, set_by=result.set_by, set_at=result.set_at,
        )


class BillableRequest(BaseModel):
    billable: StrictBool = Field(
        description="True raises the cap of the flight's billing to its contracted volume plus its carry-over."
    )


class BillableResponse(BaseModel):
    flight_id: int
    carryover: int = Field(description="The flight's carry-over, which this request does not change.")
    billable: bool
    set_by: int = Field(description="The user who set the flag.")
    set_at: datetime = Field(description="When the flag was set.")

    @classmethod
    def from_result(cls, result: BillableResult) -> "BillableResponse":
        return cls(
            flight_id=result.flight_id, carryover=result.carryover, billable=result.billable, set_by=result.set_by,
            set_at=result.set_at,
        )
