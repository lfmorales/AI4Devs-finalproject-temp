"""Pacing, the missing-data flag and the ordering of the daily status, over figures from a fake repository."""

from datetime import date

from app.application.services.campaign_status_service import CampaignStatusService
from app.domain.entities.campaign_status import FlightDeliveryFigures
from app.domain.repositories.campaign_status_repository import CampaignStatusRepository
from app.domain.services.pacing import PacingStatus

TODAY = date(2026, 8, 11)  # D; D-1 is 10 August


class FakeStatusRepository(CampaignStatusRepository):
    def __init__(self, figures: list[FlightDeliveryFigures]) -> None:
        self._figures = figures
        self.requested_as_of: date | None = None

    def list_running_flights(self, as_of: date) -> list[FlightDeliveryFigures]:
        self.requested_as_of = as_of
        return self._figures


def _figures(
    *,
    campaign_id: int = 1,
    campaign_name: str = "Campaign",
    agency_name: str = "Agency",
    line_number: int = 1,
    contracted: int = 3_100,
    delivered: int = 1_000,
    latest: date | None = date(2026, 8, 10),
) -> FlightDeliveryFigures:
    # A 31-day flight, 10 days elapsed at D-1: 1_000 impressions are expected.
    return FlightDeliveryFigures(
        campaign_id=campaign_id, campaign_name=campaign_name, agency_id=1, agency_name=agency_name,
        line_number=line_number, campaign_period_id=1, period_year=2026, period_month=8,
        flight_start=date(2026, 8, 1), flight_end=date(2026, 8, 31), contracted_impressions=contracted,
        delivered_impressions=delivered, campaign_latest_delivery_date=latest,
    )


def _rows(*figures: FlightDeliveryFigures):
    repository = FakeStatusRepository(list(figures))
    rows = CampaignStatusService(repository, today=lambda: TODAY).list_status()
    assert repository.requested_as_of == date(2026, 8, 10)
    return rows


def test_a_row_carries_contracted_delivered_ratio_and_pacing():
    [row] = _rows(_figures(contracted=3_100, delivered=1_000))

    assert (row.contracted_impressions, row.delivered_impressions) == (3_100, 1_000)
    assert row.delivery_ratio == 1_000 / 3_100
    assert row.pacing.expected_impressions == 1_000
    assert row.pacing.deviation == 0
    assert row.pacing.days_remaining == 21
    assert row.pacing_flag is False


def test_a_flight_far_behind_what_is_expected_raises_the_pacing_flag():
    [row] = _rows(_figures(delivered=0))

    assert row.pacing.status is PacingStatus.UNDER_DELIVERING
    assert row.pacing_flag is True


def test_a_flight_far_ahead_raises_the_pacing_flag():
    [row] = _rows(_figures(delivered=2_000))

    assert row.pacing.status is PacingStatus.OVER_DELIVERING
    assert row.pacing_flag is True


def test_the_missing_data_flag_is_raised_when_the_latest_delivery_predates_d_minus_1():
    [row] = _rows(_figures(latest=date(2026, 8, 9)))

    assert row.missing_data_flag is True


def test_the_missing_data_flag_is_not_raised_with_delivery_on_d_minus_1():
    [row] = _rows(_figures(latest=date(2026, 8, 10)))

    assert row.missing_data_flag is False


def test_a_campaign_with_no_delivery_at_all_is_flagged():
    [row] = _rows(_figures(latest=None, delivered=0))

    assert row.missing_data_flag is True


def test_rows_with_any_flag_come_first_then_agency_campaign_and_line():
    rows = _rows(
        _figures(campaign_id=1, campaign_name="B ok", agency_name="Alpha"),
        _figures(campaign_id=2, campaign_name="A ok", agency_name="Beta"),
        _figures(campaign_id=3, campaign_name="Z missing", agency_name="Beta", latest=None),
        _figures(campaign_id=4, campaign_name="C pacing", agency_name="Alpha", delivered=0),
        _figures(campaign_id=4, campaign_name="C pacing", agency_name="Alpha", delivered=0, line_number=2),
        _figures(campaign_id=1, campaign_name="B ok", agency_name="Alpha", line_number=2),
    )

    assert [(r.campaign_name, r.line_number) for r in rows] == [
        ("C pacing", 1), ("C pacing", 2), ("Z missing", 1),   # flagged: agency Alpha before Beta
        ("B ok", 1), ("B ok", 2), ("A ok", 1),                # not flagged: Alpha before Beta
    ]
