"""Pacing, the missing-data flag and the ordering of the daily status, over figures from a fake repository."""

from datetime import date
from decimal import Decimal

from app.application.services.campaign_status_service import CampaignStatusService
from app.domain.entities.campaign_status import FlightDeliveryFigures
from app.domain.repositories.campaign_status_repository import CampaignStatusRepository
from app.domain.services.pacing import PacingStatus
from app.domain.value_objects.volume_commitment import VolumeCommitment

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
    delivery_metric: str = "impressions",
    delivered_volume: Decimal | None = None,
    volume_commitment: VolumeCommitment = VolumeCommitment.COMMITTED,
    carryover: int = 0,
    flight_id: int = 1,
) -> FlightDeliveryFigures:
    # A 31-day flight, 10 days elapsed at D-1: 1_000 impressions are expected.
    return FlightDeliveryFigures(
        campaign_id=campaign_id, campaign_name=campaign_name, agency_id=1, agency_name=agency_name,
        line_number=line_number, campaign_period_id=1, period_year=2026, period_month=8,
        flight_start=date(2026, 8, 1), flight_end=date(2026, 8, 31), contracted_impressions=contracted,
        delivery_metric=delivery_metric,
        delivered=Decimal(delivered) if delivered_volume is None else delivered_volume,
        delivered_impressions=delivered, campaign_latest_delivery_date=latest, volume_commitment=volume_commitment,
        carryover=carryover, flight_id=flight_id,
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


# --- The pacing uses the delivery target: the contracted volume plus the carry-over (campaign/daily-status) -----------


def test_the_pacing_expects_the_delivery_target_not_the_contracted_volume() -> None:
    # 3,100 contracted + 3,100 carried in = 6,200 to deliver over 31 days: 2,000 expected after 10 days.
    [row] = _rows(_figures(contracted=3_100, carryover=3_100, delivered=1_900))

    assert row.pacing.expected_impressions == 2_000
    assert row.pacing.deviation == Decimal("-0.05")
    assert row.pacing_flag is False


def test_the_same_delivery_without_the_carry_over_is_far_ahead_and_flagged() -> None:
    [row] = _rows(_figures(contracted=3_100, carryover=0, delivered=1_900))

    assert row.pacing.expected_impressions == 1_000
    assert row.pacing.status is PacingStatus.OVER_DELIVERING
    assert row.pacing_flag is True


def test_a_carry_over_makes_a_flight_that_paced_well_fall_behind() -> None:
    [row] = _rows(_figures(contracted=3_100, carryover=3_100, delivered=1_000))

    assert row.pacing.status is PacingStatus.UNDER_DELIVERING
    assert row.pacing_flag is True


def test_the_ratio_is_the_delivered_volume_over_the_delivery_target() -> None:
    [row] = _rows(_figures(contracted=3_100, carryover=3_100, delivered=1_550))

    assert row.delivery_ratio == 1_550 / 6_200


def test_a_row_carries_the_flight_the_carry_over_and_the_delivery_target_and_keeps_the_contracted_volume() -> None:
    [row] = _rows(_figures(contracted=3_100, carryover=900, flight_id=42))

    assert (row.flight_id, row.contracted_impressions, row.carryover, row.delivery_target) == (42, 3_100, 900, 4_000)


def test_a_flight_without_a_carry_over_has_a_delivery_target_equal_to_its_contracted_volume() -> None:
    [row] = _rows(_figures(contracted=3_100))

    assert (row.carryover, row.delivery_target) == (0, 3_100)


def test_a_target_flight_with_a_carry_over_is_flagged_only_below_its_delivery_target() -> None:
    ahead = _figures(contracted=3_100, carryover=3_100, delivered=2_500, volume_commitment=VolumeCommitment.TARGET)
    behind = _figures(contracted=3_100, carryover=3_100, delivered=1_000, volume_commitment=VolumeCommitment.TARGET)

    [over] = _rows(ahead)
    [under] = _rows(behind)

    assert (over.pacing.status, over.pacing_flag) == (PacingStatus.OVER_DELIVERING, False)
    assert (under.pacing.status, under.pacing_flag) == (PacingStatus.UNDER_DELIVERING, True)


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


def test_a_dooh_row_carries_its_ots_and_its_impressions_and_the_ratio_is_on_the_ots() -> None:
    [row] = _rows(_figures(
        contracted=300_000, delivered=4_800, delivered_volume=Decimal("95000.7500"), delivery_metric="ots",
    ))

    assert row.delivered == Decimal("95000.7500")
    assert row.delivered_impressions == 4_800
    assert row.delivery_metric == "ots"
    assert row.delivery_ratio == float(Decimal("95000.7500")) / 300_000


def test_a_ctv_row_carries_its_impressions_in_both_figures() -> None:
    [row] = _rows(_figures(contracted=3_100, delivered=1_000, delivery_metric="impressions"))

    assert row.delivered == Decimal(1_000) and row.delivered_impressions == 1_000
    assert row.delivery_metric == "impressions"


def test_a_dooh_flight_with_impressions_but_no_ots_is_under_delivering() -> None:
    [row] = _rows(_figures(contracted=3_100, delivered=4_800, delivered_volume=Decimal(0), delivery_metric="ots"))

    assert row.pacing.status is PacingStatus.UNDER_DELIVERING
    assert row.pacing_flag is True


def test_a_dooh_flight_on_pace_in_ots_is_not_flagged_whatever_its_impressions() -> None:
    [row] = _rows(_figures(
        contracted=3_100, delivered=12, delivered_volume=Decimal("1000.0000"), delivery_metric="ots",
    ))

    assert row.pacing.deviation == 0
    assert row.pacing_flag is False


# --- The pacing flag by commitment: a target line may deliver above its target ---------------------------------------

def test_a_target_row_above_its_target_reports_over_delivery_without_a_flag_and_names_its_commitment() -> None:
    [row] = _rows(_figures(delivered=1_200, volume_commitment=VolumeCommitment.TARGET))

    assert row.volume_commitment is VolumeCommitment.TARGET
    assert (row.pacing.deviation, row.pacing.status) == (Decimal("0.2"), PacingStatus.OVER_DELIVERING)
    assert row.pacing_flag is False


def test_a_target_row_below_its_target_is_flagged() -> None:
    [row] = _rows(_figures(delivered=850, volume_commitment=VolumeCommitment.TARGET))

    assert row.pacing_flag is True


def test_a_committed_row_above_its_volume_is_still_flagged_and_names_its_commitment() -> None:
    [row] = _rows(_figures(delivered=1_200))

    assert row.volume_commitment is VolumeCommitment.COMMITTED
    assert row.pacing_flag is True


def test_a_target_row_above_its_target_does_not_sort_among_the_flagged_rows() -> None:
    # Agencies A, B and C: the target row of A at +20 % sorts after the flagged committed row of C.
    rows = _rows(
        _figures(campaign_id=1, agency_name="A", delivered=1_200, volume_commitment=VolumeCommitment.TARGET),
        _figures(campaign_id=2, agency_name="B", delivered=1_000),
        _figures(campaign_id=3, agency_name="C", delivered=1_200),
    )

    assert [(row.agency_name, row.pacing_flag) for row in rows] == [("C", True), ("A", False), ("B", False)]
