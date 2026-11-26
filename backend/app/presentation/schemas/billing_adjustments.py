from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer

from app.application.services.billing_adjustment_service import AdjustmentResult
from app.domain.value_objects.billing import AdjustmentEntry
from app.presentation.schemas.margin import StrictDecimal

_CENT = Decimal("0.01")

# An amount leaves as a decimal string with exactly two decimals, whatever the request wrote ("4200.5" is "4200.50").
MoneyString = Annotated[Decimal, PlainSerializer(lambda value: format(value.quantize(_CENT), "f"), return_type=str)]


class AdjustmentRequest(BaseModel):
    basis: Literal["minimum", "delivered", "contracted", "custom"] = Field(
        description=(
            "`minimum` is the rule of the lesser of delivered and the cap; `delivered` bills the delivered volume with "
            "no cap; `contracted` bills the cap (the contracted volume, plus the carry-over when it is billable); "
            "`custom` bills the amount. The first three are recomputed until the closing."
        )
    )
    amount: StrictDecimal | None = Field(
        default=None,
        description="Only with `custom`: a decimal string, zero or above, with at most two decimals.",
    )
    reason: str = Field(description="Why. Mandatory: an empty or blank reason is refused.")


class AdjustmentItem(BaseModel):
    """An adjustment with its reason. Only operations and finance read it: trading and business receive nothing."""

    id: int
    flight_id: int
    basis: str
    amount: MoneyString | None
    reason: str
    created_by: int = Field(description="The user who made it.")
    created_at: datetime

    @classmethod
    def from_entry(cls, entry: AdjustmentEntry) -> "AdjustmentItem":
        return cls(
            id=entry.entry_id, flight_id=entry.flight_id, basis=entry.adjustment.basis.value,
            amount=entry.adjustment.amount, reason=entry.reason, created_by=entry.created_by,
            created_at=entry.created_at,
        )


class AdjustmentResponse(AdjustmentItem):
    billing: MoneyString = Field(description="What the flight bills after this adjustment, two decimals.")

    @classmethod
    def from_result(cls, result: AdjustmentResult) -> "AdjustmentResponse":
        return cls(**AdjustmentItem.from_entry(result.entry).model_dump(), billing=result.billing)


class HistoryItem(AdjustmentItem):
    in_force: bool = Field(description="Whether it is the latest of the flight, the one that prices it.")


class AdjustmentHistoryResponse(BaseModel):
    adjustments: list[HistoryItem] = Field(description="Every adjustment of the flight, latest first.")

    @classmethod
    def from_entries(cls, entries: list[AdjustmentEntry]) -> "AdjustmentHistoryResponse":
        return cls(adjustments=[
            HistoryItem(**AdjustmentItem.from_entry(entry).model_dump(), in_force=index == 0)
            for index, entry in enumerate(entries)
        ])
