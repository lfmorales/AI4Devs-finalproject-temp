"""Registration builds one line per purchase-order line, numbered, dated, and split into flights."""

import asyncio
from datetime import date

import pytest

from app.application.services.campaign_registration_service import CampaignRegistrationService
from app.domain.exceptions import (
    FlightVolumeNotPositiveError,
    FlightVolumesIncompleteError,
    FlightVolumesMismatchError,
    LineDatesInvalidError,
    LineDatesOutsideCampaignError,
    VolumeTooSmallForFlightsError,
)
from tests.fixtures.in_memory_campaign_registration import (
    InMemoryCampaignRepository,
    InMemoryMasterRepository,
    InMemoryPurchaseOrderRepository,
)


def _line(**overrides: object) -> dict:
    fields: dict = {
        "dsp_id": 1, "channel_id": 1, "format_id": 1, "scope": "national", "market_description": "Spain",
        "contracted_impressions": 100, "sale_cpm": "5.00", "start_date": None, "end_date": None,
        "monthly_volumes": None,
    }
    fields.update(overrides)
    return fields


def _register(lines: list[dict], start: date = date(2026, 8, 1), end: date = date(2026, 10, 31), channels=frozenset()):
    campaign_repo = InMemoryCampaignRepository()
    purchase_orders = InMemoryPurchaseOrderRepository()
    service = CampaignRegistrationService(campaign_repo, purchase_orders, InMemoryMasterRepository(channels))
    try:
        campaign = asyncio.run(service.register_campaign(
            name="Fixture", display_name="Fixture", agency_id=1, advertiser_id=1, campaign_type_id=1,
            sector_id=1, sales_rep_id=1, start_date=start, end_date=end, order_reference="PO-1",
            order_received_on=date(2026, 7, 1), lines_data=lines,
        ))
    except Exception:
        # Whatever the failure, nothing may have been stored or created beforehand.
        assert campaign_repo.saved == []
        assert purchase_orders.orders == [] and purchase_orders.versions == []
        raise
    return campaign, campaign_repo, purchase_orders


def test_one_line_over_three_months_gets_three_flights_that_add_up_to_its_total():
    campaign, _, _ = _register([_line()])

    assert len(campaign.lines) == 1 and len(campaign.periods) == 3
    line = campaign.lines[0]
    assert [(f.period_year, f.period_month) for f in line.flights] == [(2026, 8), (2026, 9), (2026, 10)]
    assert [f.contracted_impressions for f in line.flights] == [34, 32, 34]
    assert sum(f.contracted_impressions for f in line.flights) == line.volume.contracted_impressions


def test_the_line_takes_the_campaign_dates_when_it_gives_none():
    campaign, _, _ = _register([_line()])

    assert (campaign.lines[0].start_date, campaign.lines[0].end_date) == (date(2026, 8, 1), date(2026, 10, 31))


def test_lines_are_numbered_in_the_order_of_the_purchase_order():
    campaign, _, _ = _register([_line(format_id=1), _line(format_id=2), _line(format_id=3)])

    assert [(line.line_number, line.format_id) for line in campaign.lines] == [(1, 1), (2, 2), (3, 3)]


def test_two_lines_over_two_months_are_two_lines_with_two_flights_each_and_no_copies():
    campaign, _, _ = _register([_line(), _line(format_id=2)], end=date(2026, 9, 30))

    assert len(campaign.lines) == 2 and len(campaign.periods) == 2
    assert [len(line.flights) for line in campaign.lines] == [2, 2]


def test_a_line_inside_one_month_has_one_flight_with_the_total():
    campaign, _, _ = _register([_line(contracted_impressions=777)], end=date(2026, 8, 31))

    assert [f.contracted_impressions for f in campaign.lines[0].flights] == [777]


def test_a_line_starting_late_and_one_ending_early_only_have_the_flights_that_intersect():
    campaign, _, _ = _register([
        _line(start_date=date(2026, 9, 10), contracted_impressions=1000),
        _line(end_date=date(2026, 8, 20), format_id=2, contracted_impressions=1000),
    ])

    late, early = campaign.lines
    assert [(f.period_month, f.flight_start, f.flight_end) for f in late.flights] == [
        (9, date(2026, 9, 10), date(2026, 9, 30)), (10, date(2026, 10, 1), date(2026, 10, 31)),
    ]
    assert [(f.period_month, f.flight_end) for f in early.flights] == [(8, date(2026, 8, 20))]
    assert early.flights[0].contracted_impressions == 1000


def test_explicit_monthly_volumes_are_used_as_given():
    volumes = [{"year": 2026, "month": 8, "volume": 10}, {"year": 2026, "month": 9, "volume": 20},
               {"year": 2026, "month": 10, "volume": 70}]

    campaign, _, _ = _register([_line(monthly_volumes=volumes)])

    assert [f.contracted_impressions for f in campaign.lines[0].flights] == [10, 20, 70]


@pytest.mark.parametrize(("volumes", "error"), [
    ([{"year": 2026, "month": 8, "volume": 50}, {"year": 2026, "month": 9, "volume": 50}], FlightVolumesIncompleteError),
    ([{"year": 2026, "month": 8, "volume": 50}, {"year": 2026, "month": 9, "volume": 25},
      {"year": 2026, "month": 9, "volume": 25}, {"year": 2026, "month": 10, "volume": 0}], FlightVolumesIncompleteError),
    ([{"year": 2026, "month": 8, "volume": 30}, {"year": 2026, "month": 9, "volume": 30},
      {"year": 2026, "month": 10, "volume": 30}], FlightVolumesMismatchError),
    ([{"year": 2026, "month": 8, "volume": 0}, {"year": 2026, "month": 9, "volume": 50},
      {"year": 2026, "month": 10, "volume": 50}], FlightVolumeNotPositiveError),
])
def test_invalid_explicit_volumes_are_refused_and_nothing_is_stored(volumes, error):
    with pytest.raises(error):
        _register([_line(monthly_volumes=volumes)])


def test_line_dates_outside_the_campaign_are_refused():
    with pytest.raises(LineDatesOutsideCampaignError):
        _register([_line(start_date=date(2026, 7, 31))])
    with pytest.raises(LineDatesOutsideCampaignError):
        _register([_line(end_date=date(2026, 11, 1))])


def test_a_start_after_the_campaign_end_with_no_end_given_is_invalid_dates():
    with pytest.raises(LineDatesInvalidError):
        _register([_line(start_date=date(2026, 11, 5))])


def test_a_total_that_leaves_a_flight_at_zero_is_refused():
    with pytest.raises(VolumeTooSmallForFlightsError):
        _register([_line(contracted_impressions=2)])


def test_a_total_exactly_big_enough_for_every_flight_is_accepted():
    campaign, _, _ = _register([_line(contracted_impressions=3)])

    assert sorted(f.contracted_impressions for f in campaign.lines[0].flights) == [1, 1, 1]


def test_a_bad_second_line_leaves_nothing_stored_not_even_the_purchase_order():
    with pytest.raises(LineDatesOutsideCampaignError):
        _register([_line(), _line(format_id=2, end_date=date(2027, 1, 1))])


def test_an_unknown_channel_is_refused_before_anything_is_written():
    with pytest.raises(ValueError):
        _register([_line(), _line(channel_id=99)], channels=frozenset({99}))


def test_the_purchase_order_version_is_linked_to_every_line():
    campaign, _, purchase_orders = _register([_line(), _line(format_id=2)])

    assert purchase_orders.versions == [1]
    assert {line.purchase_order_version_id for line in campaign.lines} == {1}


def test_the_saved_campaign_is_the_one_returned():
    campaign, campaign_repo, _ = _register([_line()])

    assert campaign_repo.saved == [campaign]
