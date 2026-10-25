"""The campaign repository saves campaign, periods, lines and flights in one transaction."""

import asyncio
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.application.services.campaign_registration_service import CampaignRegistrationService
from app.domain.entities.campaign import Campaign
from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
)
from app.infrastructure.persistence.repositories import CampaignRepositoryImpl
from tests.fixtures.in_memory_campaign_registration import InMemoryMasterRepository, InMemoryPurchaseOrderRepository
from tests.fixtures.master_data import seed_master_data


def _line(**overrides: object) -> dict:
    fields: dict = {
        "dsp_id": 1, "channel_id": 1, "format_id": 1, "scope": "national", "market_description": "Spain",
        "contracted_impressions": 1000, "sale_cpm": "5.00", "start_date": None, "end_date": None,
        "monthly_volumes": None,
    }
    fields.update(overrides)
    return fields


def _campaign(lines: list[dict], end: date = date(2026, 10, 31)) -> Campaign:
    """A campaign built by the registration service over in-memory doubles, so nothing is saved yet."""
    from tests.fixtures.in_memory_campaign_registration import InMemoryCampaignRepository

    service = CampaignRegistrationService(
        InMemoryCampaignRepository(), InMemoryPurchaseOrderRepository(), InMemoryMasterRepository()
    )
    campaign = asyncio.run(service.register_campaign(
        name="Repository fixture", display_name="Repository fixture", agency_id=1, advertiser_id=1,
        campaign_type_id=1, sector_id=1, sales_rep_id=1, start_date=date(2026, 8, 1), end_date=end,
        order_reference="PO-REPO", order_received_on=date(2026, 7, 1), lines_data=lines,
    ))
    campaign.purchase_order_id = None
    for line in campaign.lines:
        line.purchase_order_version_id = None
    return campaign


def _count(session, record) -> int:
    return session.scalar(select(func.count()).select_from(record))


@pytest.fixture
def session(rolled_back_session):
    seed_master_data(rolled_back_session)
    return rolled_back_session


def _save(session, campaign: Campaign) -> int:
    return asyncio.run(CampaignRepositoryImpl(session).save(campaign))


def test_campaign_periods_lines_and_flights_are_all_stored(session):
    campaign = _campaign([_line(), _line(format_id=2)])

    _save(session, campaign)

    assert _count(session, CampaignRecord) == 1
    assert _count(session, CampaignPeriodRecord) == 3
    assert _count(session, CampaignLineRecord) == 2
    assert _count(session, CampaignLinePeriodRecord) == 6


def test_a_line_is_stored_under_its_campaign_with_its_number_and_dates(session):
    campaign = _campaign([_line(), _line(format_id=2, start_date=date(2026, 9, 5), end_date=date(2026, 9, 25))])

    campaign_id = _save(session, campaign)

    rows = session.scalars(select(CampaignLineRecord).order_by(CampaignLineRecord.line_number)).all()
    assert [(r.campaign_id, r.line_number, r.start_date, r.end_date) for r in rows] == [
        (campaign_id, 1, date(2026, 8, 1), date(2026, 10, 31)),
        (campaign_id, 2, date(2026, 9, 5), date(2026, 9, 25)),
    ]


def test_each_flight_points_at_the_period_of_its_own_month(session):
    campaign = _campaign([_line()])

    _save(session, campaign)

    rows = session.execute(
        select(CampaignPeriodRecord.period_month, CampaignLinePeriodRecord.flight_start,
               CampaignLinePeriodRecord.contracted_impressions)
        .join(CampaignLinePeriodRecord, CampaignLinePeriodRecord.campaign_period_id == CampaignPeriodRecord.id)
        .order_by(CampaignPeriodRecord.period_month)
    ).all()
    assert [(month, start.month, volume) for month, start, volume in rows] == [(8, 8, 337), (9, 9, 326), (10, 10, 337)]


def test_periods_are_resolved_by_year_and_month_and_not_by_position(session):
    campaign = _campaign([_line()])
    campaign.periods.reverse()  # October first: a lookup by position would swap every month

    _save(session, campaign)

    rows = session.execute(
        select(CampaignPeriodRecord.period_month, CampaignLinePeriodRecord.flight_start)
        .join(CampaignLinePeriodRecord, CampaignLinePeriodRecord.campaign_period_id == CampaignPeriodRecord.id)
    ).all()
    assert rows and all(month == start.month for month, start in rows)


def test_identifiers_are_handed_back_to_the_entities(session):
    campaign = _campaign([_line()])

    campaign_id = _save(session, campaign)

    assert campaign.id == campaign_id
    assert all(period.id and period.campaign_id == campaign_id for period in campaign.periods)
    period_ids = {period.id for period in campaign.periods}
    line = campaign.lines[0]
    assert line.id and line.campaign_id == campaign_id
    assert all(flight.id and flight.campaign_period_id in period_ids for flight in line.flights)


def test_a_failure_while_storing_a_line_leaves_nothing_stored(session):
    campaign = _campaign([_line(), _line(format_id=2)])
    campaign.lines[1].channel_id = 0  # no such channel: the foreign key refuses the second line

    with pytest.raises(IntegrityError):
        _save(session, campaign)

    for record in (CampaignRecord, CampaignPeriodRecord, CampaignLineRecord, CampaignLinePeriodRecord):
        assert _count(session, record) == 0


def test_a_line_without_flights_is_refused_and_nothing_is_stored(session):
    campaign = _campaign([_line()])
    campaign.lines[0].flights = []

    with pytest.raises(ValueError):
        _save(session, campaign)

    assert _count(session, CampaignRecord) == 0 and _count(session, CampaignLineRecord) == 0
