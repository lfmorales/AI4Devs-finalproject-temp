"""The volumes of the responses are in the unit of the delivery metric; the schemas say so."""

from pydantic import BaseModel
import pytest

from app.presentation.schemas.campaign_status import CampaignStatusResponse, PacingResponse
from app.presentation.schemas.margin import (
    ClosingResponse,
    DeliveryChangeResponse,
    FlightMarginResponse,
    TotalsResponse,
)


@pytest.mark.parametrize(("schema", "field"), [
    (CampaignStatusResponse, "contracted_impressions"),
    (CampaignStatusResponse, "delivered"),
    (PacingResponse, "expected_impressions"),
    (FlightMarginResponse, "contracted_impressions"),
    (FlightMarginResponse, "delivered"),
    (TotalsResponse, "contracted_impressions"),
    (TotalsResponse, "delivered"),
])
def test_a_volume_field_says_it_is_in_the_unit_of_delivery_metric(schema: type[BaseModel], field: str) -> None:
    description = schema.model_fields[field].description

    assert description is not None and "delivery_metric" in description


@pytest.mark.parametrize(("schema", "field"), [
    (FlightMarginResponse, "delivery_change"),
    (DeliveryChangeResponse, "current_margin"),
])
def test_the_current_margin_is_described_as_informative(schema: type[BaseModel], field: str) -> None:
    description = schema.model_fields[field].description

    assert description is not None
    assert "closing's rebate and rates" in description
    assert "cap and billing basis" in description
    assert "today's delivery" in description
    assert "no amount or total adds it" in description


@pytest.mark.parametrize(("schema", "field", "words"), [
    (FlightMarginResponse, "delivery_changed", ("closed", "delivery")),
    (TotalsResponse, "delivery_changed_count", ("delivery_changed",)),
    (ClosingResponse, "closings", ("closing", "month")),
    (FlightMarginResponse, "billable", ("delivery_metric", "four decimals", "target", "custom", "closed before")),
    (FlightMarginResponse, "billing_basis", ("minimum", "delivered", "contracted", "custom", "reported")),
    (DeliveryChangeResponse, "billable_difference", ("four decimals", "target", "closed before")),
    (DeliveryChangeResponse, "billing_difference", ("two decimals", "target", "closed before")),
])
def test_the_new_fields_are_described(schema: type[BaseModel], field: str, words: tuple[str, ...]) -> None:
    description = schema.model_fields[field].description

    assert description is not None and all(word in description for word in words)
