import pytest
from datetime import date
from decimal import Decimal

from app.domain.entities.campaign import Campaign, CampaignLine, CampaignLineFlight, CampaignPeriod
from app.domain.value_objects.contracted_volume import ContractedVolume


def test_campaign_with_periods():
    """Test campaign with auto-expanded periods."""
    campaign = Campaign(
        id=None,
        name="CAMP-2026-001",
        display_name="Campaign 2026 Q1",
        agency_id=1,
        advertiser_id=2,
        campaign_type_id=3,
        sector_id=4,
        sales_rep_id=5,
        purchase_order_id=None,
        start_date=date(2026, 1, 15),
        end_date=date(2026, 3, 10),
        status="active",
        periods=[],
        lines=[]
    )

    assert campaign.name == "CAMP-2026-001"
    assert len(campaign.periods) == 0  # Periods are added separately


def test_campaign_period_construction_with_campaign_id():
    """Test that CampaignPeriod can be constructed with campaign_id and all values."""
    period = CampaignPeriod(
        period_year=2026,
        period_month=6,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        id=42,
        campaign_id=10,
        status="open"
    )

    assert period.period_year == 2026
    assert period.period_month == 6
    assert period.period_start == date(2026, 6, 1)
    assert period.period_end == date(2026, 6, 30)
    assert period.id == 42
    assert period.campaign_id == 10
    assert period.status == "open"


def test_campaign_line_with_contracted_volume():
    """Test campaign line with contracted volume."""
    volume = ContractedVolume(
        contracted_impressions=500_000,
        sale_cpm=Decimal("15.25")
    )

    line = CampaignLine(
        id=None,
        campaign_period_id=1,
        purchase_order_version_id=1,
        dsp_id=1,
        channel_id=1,
        format_id=1,
        scope="national",
        market_description="Spain digital",
        volume=volume,
        currency="EUR"
    )

    assert line.scope == "national"
    assert line.volume.revenue() == Decimal("7625.00")  # 500k * 15.25 / 1000


def test_campaign_line_rejects_invalid_scope():
    """Test that invalid scope is rejected."""
    volume = ContractedVolume(
        contracted_impressions=100_000,
        sale_cpm=Decimal("10.00")
    )

    with pytest.raises(ValueError):
        CampaignLine(
            id=None,
            campaign_period_id=1,
            purchase_order_version_id=1,
            dsp_id=1,
            channel_id=1,
            format_id=1,
            scope="regional",  # Invalid scope
            market_description="Test",
            volume=volume,
            currency="EUR"
        )


def test_campaign_line_hangs_from_the_campaign_with_its_own_dates_and_flights():
    flight = CampaignLineFlight(
        period_year=2026,
        period_month=8,
        flight_start=date(2026, 8, 15),
        flight_end=date(2026, 8, 31),
        contracted_impressions=400_000,
    )

    line = CampaignLine(
        id=None,
        purchase_order_version_id=None,
        dsp_id=1,
        channel_id=1,
        format_id=1,
        scope="national",
        market_description="Spain digital",
        volume=ContractedVolume(contracted_impressions=400_000, sale_cpm=Decimal("5.00")),
        campaign_id=7,
        line_number=2,
        start_date=date(2026, 8, 15),
        end_date=date(2026, 8, 31),
        flights=[flight],
    )

    assert (line.campaign_id, line.line_number) == (7, 2)
    assert (line.start_date, line.end_date) == (date(2026, 8, 15), date(2026, 8, 31))
    assert line.flights == [flight]
    assert flight.campaign_period_id is None and flight.id is None


def test_a_line_starts_without_flights_or_dates():
    line = CampaignLine(
        id=None, purchase_order_version_id=None, dsp_id=1, channel_id=1, format_id=1,
        scope="national", market_description="Spain",
        volume=ContractedVolume(contracted_impressions=1, sale_cpm=Decimal("1.00")),
    )

    assert line.flights == []
    assert (line.campaign_id, line.line_number, line.start_date, line.end_date) == (None, None, None, None)
