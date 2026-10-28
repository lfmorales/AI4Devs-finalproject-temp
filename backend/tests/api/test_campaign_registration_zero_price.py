"""A line may be registered without a sale price, never with a negative one, and never without volume."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.infrastructure.persistence.models import CampaignLineRecord, CampaignRecord
from tests.api.test_campaign_registration_flights import _line, _payload


def _counts(session) -> tuple[int, int]:
    return (
        session.scalar(select(func.count()).select_from(CampaignRecord)),
        session.scalar(select(func.count()).select_from(CampaignLineRecord)),
    )


def _fields_named(response) -> set[str]:
    return {str(part) for item in response.json()["detail"] for part in item["loc"]}


@pytest.mark.parametrize("cpm", ["0.00", "0", "0.0"])
def test_a_line_with_a_zero_price_and_positive_volume_is_registered(authenticated_client, test_db_session, cpm):
    response = authenticated_client.post("/campaigns", json=_payload([_line(contracted_impressions=500_000, sale_cpm=cpm)]))

    assert response.status_code == 201, response.text
    (line,) = response.json()["lines"]
    assert Decimal(line["sale_cpm"]) == 0
    stored = test_db_session.scalars(select(CampaignLineRecord)).one()
    assert stored.sale_cpm == Decimal("0.00") and stored.contracted_impressions == 500_000


def test_a_line_without_a_price_has_the_same_flights_and_split_as_a_priced_one(authenticated_client):
    free = authenticated_client.post("/campaigns", json=_payload([_line(contracted_impressions=1000, sale_cpm="0.00")], name="CAMP-FREE"))
    priced = authenticated_client.post("/campaigns", json=_payload([_line(contracted_impressions=1000, sale_cpm="5.00")], name="CAMP-PRICED"))

    def shape(response):
        return [
            (f["period_year"], f["period_month"], f["flight_start"], f["flight_end"], f["contracted_impressions"])
            for f in response.json()["lines"][0]["flights"]
        ]

    assert free.status_code == priced.status_code == 201
    assert shape(free) == shape(priced)
    assert len(shape(free)) == 3


@pytest.mark.parametrize("cpm", ["-1.00", "-0.01", "-100"])
def test_a_negative_price_is_rejected_and_nothing_is_stored(authenticated_client, test_db_session, cpm):
    before = _counts(test_db_session)

    response = authenticated_client.post("/campaigns", json=_payload([_line(sale_cpm=cpm)]))

    assert response.status_code == 422
    assert "sale_cpm" in _fields_named(response)
    assert _counts(test_db_session) == before


@pytest.mark.parametrize("cpm", ["5.00", "0.00"])
@pytest.mark.parametrize("volume", [0, -1])
def test_a_volume_of_zero_or_less_is_rejected_whatever_the_price(authenticated_client, test_db_session, cpm, volume):
    before = _counts(test_db_session)

    response = authenticated_client.post("/campaigns", json=_payload([_line(contracted_impressions=volume, sale_cpm=cpm)]))

    assert response.status_code == 422
    assert "contracted_impressions" in _fields_named(response)
    assert _counts(test_db_session) == before


def test_a_price_with_more_than_two_decimals_is_still_rejected(authenticated_client):
    assert authenticated_client.post("/campaigns", json=_payload([_line(sale_cpm="4.375")])).status_code == 422
