"""The volumes of the responses are in the unit of the delivery metric; the schemas say so."""

from pydantic import BaseModel
import pytest

from app.presentation.schemas.campaign_status import CampaignStatusResponse, PacingResponse
from app.presentation.schemas.margin import FlightMarginResponse, TotalsResponse


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
