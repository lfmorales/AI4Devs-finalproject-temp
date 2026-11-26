"""The margin of one flight: revenue, media cost, rebate and platform cost, each rounded once, half up.

Worked example (docs/product-description.md §5.8, flight model): 726,202 contracted impressions at a
sale CPM of 5.00 € give revenue 3,631.01 €; the rebate is 25 % of it, 907.7525 € exact, 907.75 € rounded;
700,000 delivered impressions at 1.00 € per thousand give a platform cost of 700.00 €. The media cost of
1,200.00 € is a placeholder, since real cost only exists in Adform.
"""

from dataclasses import fields, replace
from datetime import date
from decimal import Decimal

import pytest

from app.domain.services import flight_margin
from app.domain.services.flight_margin import calculate_flight_margin, rebate_base, round_amount
from app.domain.value_objects.margin import FlightEconomics, FlightStatus
from app.domain.value_objects.priced_flight import FlightFacts
from app.domain.value_objects.volume_commitment import VolumeCommitment
from tests.fixtures.flight_inputs import flight_economics, flight_facts

AUGUST_START = date(2026, 8, 1)
AUGUST_END = date(2026, 8, 31)
AFTER_AUGUST = date(2026, 9, 1)


def _flight(
    contracted_impressions: int = 726_202,
    sale_cpm: str = "5.00",
    delivered_impressions: int = 700_000,
    media_cost: str = "1200.00",
    rebate_amount: str = "907.7525",
    platform_rate: str = "1.00",
    flight_start: date = AUGUST_START,
    flight_end: date = AUGUST_END,
) -> FlightEconomics:
    return flight_economics(
        flight_start=flight_start,
        flight_end=flight_end,
        contracted_impressions=contracted_impressions,
        sale_cpm=Decimal(sale_cpm),
        delivered_impressions=delivered_impressions,
        media_cost=Decimal(media_cost),
        rebate_amount=Decimal(rebate_amount),
        platform_rate=Decimal(platform_rate),
    )


def test_a_closed_flight_applies_the_four_terms():
    result = calculate_flight_margin(_flight(), as_of=AFTER_AUGUST)

    assert result.status is FlightStatus.CLOSED
    assert result.revenue == Decimal("3631.01")
    assert result.media_cost == Decimal("1200.00")
    assert result.rebate == Decimal("907.75")
    assert result.platform_cost == Decimal("700.00")
    assert result.margin == Decimal("823.26")
    assert result.provisional is False
    assert result.below_cost is False


def test_every_output_amount_is_a_decimal_with_two_places():
    result = calculate_flight_margin(_flight(), as_of=AFTER_AUGUST)

    for amount in (result.revenue, result.media_cost, result.rebate, result.platform_cost, result.margin):
        assert isinstance(amount, Decimal)
        assert amount.as_tuple().exponent == -2


def test_rounding_is_half_up_not_half_even():
    assert round_amount(Decimal("0.125")) == Decimal("0.13")
    assert round_amount(Decimal("2.525")) == Decimal("2.53")
    assert round_amount(Decimal("0.124999")) == Decimal("0.12")


def test_the_rebate_is_rounded_before_the_margin_is_subtracted():
    # The margin subtracts the rounded 0.13, not the exact 0.125.
    result = calculate_flight_margin(_flight(rebate_amount="0.125"), as_of=AFTER_AUGUST)

    assert result.rebate == Decimal("0.13")
    assert result.margin == Decimal("3631.01") - Decimal("1200.00") - Decimal("0.13") - Decimal("700.00")


def test_each_amount_is_rounded_exactly_once(monkeypatch: pytest.MonkeyPatch):
    calls: list[Decimal] = []
    original = flight_margin.round_amount

    def spy(amount: Decimal) -> Decimal:
        calls.append(amount)
        return original(amount)

    monkeypatch.setattr(flight_margin, "round_amount", spy)

    calculate_flight_margin(_flight(), as_of=AFTER_AUGUST)

    assert len(calls) == 4


def test_a_float_input_is_refused():
    with pytest.raises(TypeError):
        flight_economics(
            flight_start=AUGUST_START,
            flight_end=AUGUST_END,
            contracted_impressions=1000,
            sale_cpm=5.0,  # type: ignore[arg-type]
            delivered_impressions=0,
            media_cost=Decimal("0"),
            rebate_amount=Decimal("0"),
            platform_rate=Decimal("1.00"),
        )


def test_under_delivery_does_not_reduce_revenue():
    result = calculate_flight_margin(_flight(delivered_impressions=700_000), as_of=AFTER_AUGUST)

    assert result.revenue == Decimal("3631.01")
    assert result.platform_cost == Decimal("700.00")


@pytest.mark.parametrize("delivered", [0, 700_000, 726_202, 900_000])
def test_revenue_is_the_same_whatever_was_delivered(delivered: int):
    result = calculate_flight_margin(_flight(delivered_impressions=delivered), as_of=AFTER_AUGUST)

    assert result.revenue == Decimal("3631.01")


SEPTEMBER_START = date(2026, 9, 1)
SEPTEMBER_END = date(2026, 9, 30)


def _september_flight(**overrides: object) -> FlightEconomics:
    """A 30-day flight: 300,000 contracted at 5.00 € is 1,500.00 € in full, with a flat 20 % rebate of 300.00 €."""
    values: dict[str, object] = {
        "contracted_impressions": 300_000,
        "sale_cpm": "5.00",
        "delivered_impressions": 90_000,
        "media_cost": "150.00",
        "rebate_amount": "300.00",
        "platform_rate": "1.00",
        "flight_start": SEPTEMBER_START,
        "flight_end": SEPTEMBER_END,
    }
    values.update(overrides)
    return _flight(**values)  # type: ignore[arg-type]


def test_a_running_flight_is_pro_rated_by_elapsed_days_of_its_window():
    # Ten of thirty days have elapsed on September 10th:
    #   revenue  1,500.00 x 10 / 30 = 500.00
    #   rebate     300.00 x 10 / 30 = 100.00
    #   media cost and platform cost come from what was delivered, so they are not pro-rated:
    #   media cost 150.00; platform cost 90,000 / 1000 x 1.00 = 90.00
    #   margin 500.00 - 150.00 - 100.00 - 90.00 = 160.00
    result = calculate_flight_margin(_september_flight(), as_of=date(2026, 9, 10))

    assert result.status is FlightStatus.RUNNING
    assert result.revenue == Decimal("500.00")
    assert result.rebate == Decimal("100.00")
    assert result.media_cost == Decimal("150.00")
    assert result.platform_cost == Decimal("90.00")
    assert result.margin == Decimal("160.00")
    assert result.provisional is True


def test_a_running_flight_with_no_delivery_still_accrues_revenue():
    result = calculate_flight_margin(
        _september_flight(delivered_impressions=0, media_cost="0.00"), as_of=date(2026, 9, 10)
    )

    assert result.status is FlightStatus.RUNNING
    assert result.revenue == Decimal("500.00")
    assert result.platform_cost == Decimal("0.00")
    assert result.margin == Decimal("400.00")
    assert result.provisional is True


@pytest.mark.parametrize("delivered", [0, 90_000, 400_000])
def test_pro_rating_does_not_depend_on_what_was_delivered(delivered: int):
    result = calculate_flight_margin(_september_flight(delivered_impressions=delivered), as_of=date(2026, 9, 10))

    assert result.revenue == Decimal("500.00")
    assert result.rebate == Decimal("100.00")


def test_the_flight_is_closed_on_the_day_its_last_day_is_counted():
    result = calculate_flight_margin(_september_flight(), as_of=SEPTEMBER_END)

    assert result.status is FlightStatus.CLOSED
    assert result.revenue == Decimal("1500.00")
    assert result.provisional is False


def test_the_day_before_the_end_is_still_running():
    result = calculate_flight_margin(_september_flight(), as_of=date(2026, 9, 29))

    assert result.status is FlightStatus.RUNNING
    assert result.revenue == Decimal("1450.00")  # 1,500.00 x 29 / 30
    assert result.provisional is True


def test_the_first_day_of_a_flight_is_one_elapsed_day():
    result = calculate_flight_margin(_september_flight(), as_of=SEPTEMBER_START)

    assert result.status is FlightStatus.RUNNING
    assert result.revenue == Decimal("50.00")  # 1,500.00 x 1 / 30


def test_a_flight_that_has_not_started_has_no_margin():
    result = calculate_flight_margin(
        _september_flight(flight_start=date(2026, 10, 1), flight_end=date(2026, 10, 31)), as_of=SEPTEMBER_END
    )

    assert result.status is FlightStatus.NOT_STARTED
    assert result.revenue is None
    assert result.media_cost is None
    assert result.rebate is None
    assert result.platform_cost is None
    assert result.margin is None
    assert result.provisional is False
    assert result.below_cost is False


def test_a_pro_rated_amount_is_rounded_once_after_pro_rating():
    # 1,001 impressions at 5.00 € is exactly 5.005 €. Over two days, one elapsed, the exact figure is 2.5025,
    # which rounds to 2.50; rounding the full amount first (5.01) and halving it would give 2.51.
    flight = _flight(
        contracted_impressions=1001,
        rebate_amount="5.005",
        flight_start=date(2026, 9, 1),
        flight_end=date(2026, 9, 2),
        delivered_impressions=0,
        media_cost="0.00",
    )

    result = calculate_flight_margin(flight, as_of=date(2026, 9, 1))

    assert result.revenue == Decimal("2.50")
    assert result.rebate == Decimal("2.50")


def test_a_running_flight_also_rounds_each_amount_exactly_once(monkeypatch: pytest.MonkeyPatch):
    calls: list[Decimal] = []
    original = flight_margin.round_amount
    monkeypatch.setattr(flight_margin, "round_amount", lambda amount: calls.append(amount) or original(amount))

    calculate_flight_margin(_september_flight(), as_of=date(2026, 9, 10))

    # The contracted revenue, the accrued revenue, the media cost, the rebate and the platform cost.
    assert len(calls) == 5


def test_a_flight_whose_media_cost_exceeds_its_revenue_is_below_cost():
    result = calculate_flight_margin(_flight(media_cost="4000.00", rebate_amount="0"), as_of=AFTER_AUGUST)

    assert result.below_cost is True
    assert result.margin == Decimal("3631.01") - Decimal("4000.00") - Decimal("700.00")


def test_a_margin_of_exactly_zero_is_not_below_cost():
    # Revenue 3,631.01 = media cost, no rebate, no platform cost: the final margin is 0.00.
    result = calculate_flight_margin(
        _flight(media_cost="3631.01", rebate_amount="0", platform_rate="0"), as_of=AFTER_AUGUST
    )

    assert result.margin == Decimal("0.00")
    assert result.below_cost is False


def test_below_cost_judges_the_margin_made_of_rounded_amounts():
    # A media cost of 100.004 rounds to 100.00 against a revenue of 100.00: the margin is 0.00, not -0.004.
    result = calculate_flight_margin(
        _flight(contracted_impressions=10_000, sale_cpm="10.00", media_cost="100.004", rebate_amount="0", platform_rate="0"),
        as_of=AFTER_AUGUST,
    )

    assert result.revenue == Decimal("100.00") and result.media_cost == Decimal("100.00")
    assert result.margin == Decimal("0.00")
    assert result.below_cost is False


def test_a_cent_under_zero_is_below_cost():
    result = calculate_flight_margin(
        _flight(contracted_impressions=10_000, sale_cpm="10.00", media_cost="100.01", rebate_amount="0", platform_rate="0"),
        as_of=AFTER_AUGUST,
    )

    assert result.margin == Decimal("-0.01")
    assert result.below_cost is True


def test_a_flight_with_media_cost_under_revenue_is_below_cost_when_the_rebate_and_platform_take_it_under_zero():
    # Media cost 2,100.00 against revenue 3,631.01, but the rebate (907.75) and the platform cost (700.00) follow.
    result = calculate_flight_margin(_flight(media_cost="2100.00"), as_of=AFTER_AUGUST)

    assert result.media_cost < result.revenue
    assert result.margin == Decimal("-76.74")
    assert result.below_cost is True


def test_a_flight_whose_media_cost_equals_its_revenue_is_below_cost_once_the_other_costs_are_counted():
    result = calculate_flight_margin(_flight(media_cost="3631.01"), as_of=AFTER_AUGUST)

    assert result.below_cost is True


def test_a_positive_margin_is_not_below_cost_even_with_a_high_media_cost():
    result = calculate_flight_margin(
        _flight(media_cost="3000.00", rebate_amount="0", platform_rate="0.10"), as_of=AFTER_AUGUST
    )

    assert result.margin == Decimal("3631.01") - Decimal("3000.00") - Decimal("70.00")
    assert result.below_cost is False


def test_a_running_flight_can_be_below_cost():
    result = calculate_flight_margin(_september_flight(media_cost="900.00"), as_of=date(2026, 9, 10))

    assert result.below_cost is True


def _dooh_flight() -> FlightEconomics:
    # 300,000 OTS contracted at 5.00 €; 280,000.50 OTS delivered, over 12,000 real impressions.
    return flight_economics(
        flight_start=AUGUST_START, flight_end=AUGUST_END, contracted_impressions=300_000,
        sale_cpm=Decimal("5.00"), delivered_impressions=12_000, media_cost=Decimal("0.00"),
        rebate_amount=Decimal("0"), platform_rate=Decimal("1.00"),
        delivery_metric="ots", delivered=Decimal("280000.5000"),
    )


def test_a_closed_dooh_flight_earns_the_revenue_of_its_contracted_ots() -> None:
    result = calculate_flight_margin(_dooh_flight(), as_of=AFTER_AUGUST)

    assert result.revenue == Decimal("1500.00")


def test_the_platform_cost_of_a_dooh_flight_is_on_its_real_impressions_not_on_its_ots() -> None:
    result = calculate_flight_margin(_dooh_flight(), as_of=AFTER_AUGUST)

    assert result.platform_cost == Decimal("12.00")  # 12,000 impressions at 1.00 € per thousand, not 280.00 €
    assert result.margin == Decimal("1488.00")


def test_the_margin_carries_the_delivered_volume_in_the_metric_and_the_real_impressions() -> None:
    result = calculate_flight_margin(_dooh_flight(), as_of=AFTER_AUGUST)

    assert (result.delivered, result.delivered_impressions, result.delivery_metric) == (
        Decimal("280000.5000"), 12_000, "ots",
    )


def test_a_flight_counted_in_impressions_delivers_its_impressions_in_both_figures() -> None:
    result = calculate_flight_margin(_flight(), as_of=AFTER_AUGUST)

    assert (result.delivered, result.delivered_impressions, result.delivery_metric) == (
        Decimal(700_000), 700_000, "impressions",
    )


def test_a_flight_that_has_not_started_names_its_metric_and_has_no_volume() -> None:
    result = calculate_flight_margin(_dooh_flight(), as_of=date(2026, 7, 31))

    assert result.status is FlightStatus.NOT_STARTED
    assert result.delivery_metric == "ots" and result.delivered is None


# --- A target flight earns what its DSP reports (finance/margin-calculation) ---------------------------------------
#
# Worked example of a closed Deal flight: a target of 1,000,000 impressions at a sale CPM of 5.00 €, 1,100,000
# served, a reported revenue of 4,400.00 € and a buyer's spend of 5,500.00 €. Its gross is 1,100,000 / 1000 × 5.00 =
# 5,500.00 €; a flat 10 % rebate on that gross is 550.00 €; 1.00 € per thousand served is a platform cost of 1,100.00 €.

NOVEMBER_START = date(2026, 11, 1)
NOVEMBER_END = date(2026, 11, 30)
AFTER_NOVEMBER = date(2026, 12, 1)


def _target_flight(
    delivered_impressions: int = 1_100_000,
    reported_revenue: str = "4400.00",
    buyer_spend: str = "5500.00",
    data_cost: str = "0",
    rebate_amount: str = "550.00",
    sale_cpm: str = "5.00",
    volume_commitment: VolumeCommitment = VolumeCommitment.TARGET,
) -> FlightEconomics:
    return flight_economics(
        flight_start=NOVEMBER_START,
        flight_end=NOVEMBER_END,
        contracted_impressions=1_000_000,
        sale_cpm=Decimal(sale_cpm),
        delivered_impressions=delivered_impressions,
        media_cost=Decimal("0"),
        rebate_amount=Decimal(rebate_amount),
        platform_rate=Decimal("1.00"),
        volume_commitment=volume_commitment,
        reported_revenue=Decimal(reported_revenue),
        buyer_spend=Decimal(buyer_spend),
        data_cost=Decimal(data_cost),
    )


def test_the_worked_example_of_a_closed_target_flight() -> None:
    result = calculate_flight_margin(_target_flight(), as_of=AFTER_NOVEMBER)

    assert result.status is FlightStatus.CLOSED
    assert result.volume_commitment is VolumeCommitment.TARGET
    assert result.gross_revenue == Decimal("5500.00")
    assert result.revenue == Decimal("4400.00")
    assert result.media_cost == Decimal("0.00")
    assert result.rebate == Decimal("550.00")
    assert result.platform_cost == Decimal("1100.00")
    assert result.margin == Decimal("2750.00")
    assert result.margin_pct == Decimal("62.50")
    assert result.provisional is False
    assert result.below_cost is False
    assert result.zero_sale is False
    assert result.gross_differs_from_buyer_spend is False
    assert result.data_cost_reported is False


def test_a_target_flight_that_served_more_than_its_target_earns_what_is_reported_not_the_target_times_the_cpm() -> None:
    result = calculate_flight_margin(_target_flight(), as_of=AFTER_NOVEMBER)

    # The target's sale is still reported as the contracted revenue; it is not the revenue.
    assert result.contracted_revenue == Decimal("5000.00")
    assert result.revenue == Decimal("4400.00")


def test_the_reported_revenue_of_a_target_flight_is_rounded_once_half_up() -> None:
    result = calculate_flight_margin(_target_flight(reported_revenue="4400.005"), as_of=AFTER_NOVEMBER)

    assert result.revenue == Decimal("4400.01")
    assert result.margin == Decimal("2750.01")


def test_a_running_target_flight_is_not_pro_rated_and_is_provisional() -> None:
    flight = _target_flight(
        delivered_impressions=400_000, reported_revenue="1600.00", buyer_spend="2000.00", rebate_amount="200.00"
    )

    result = calculate_flight_margin(flight, as_of=date(2026, 11, 10))

    assert result.status is FlightStatus.RUNNING
    assert (result.accrued_days, result.window_days) == (10, 30)
    assert result.revenue == Decimal("1600.00")
    assert result.rebate == Decimal("200.00")
    assert result.platform_cost == Decimal("400.00")
    assert result.gross_revenue == Decimal("2000.00")
    assert result.margin == Decimal("1000.00")
    assert result.provisional is True


def test_a_target_flight_that_served_nothing_earns_nothing() -> None:
    flight = _target_flight(delivered_impressions=0, reported_revenue="0", buyer_spend="0", rebate_amount="0")

    result = calculate_flight_margin(flight, as_of=AFTER_NOVEMBER)

    assert (result.revenue, result.gross_revenue, result.rebate, result.platform_cost, result.margin) == (
        Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"),
    )
    assert result.margin_pct is None
    assert result.gross_differs_from_buyer_spend is False


def test_a_target_line_without_a_price_keeps_its_reported_revenue() -> None:
    flight = _target_flight(
        sale_cpm="0.00", delivered_impressions=10_000, reported_revenue="40.00", buyer_spend="0", rebate_amount="0"
    )

    result = calculate_flight_margin(flight, as_of=AFTER_NOVEMBER)

    assert (result.gross_revenue, result.rebate, result.revenue, result.platform_cost, result.margin) == (
        Decimal("0.00"), Decimal("0.00"), Decimal("40.00"), Decimal("10.00"), Decimal("30.00"),
    )
    assert result.zero_sale is True


def test_a_target_flight_that_has_not_started_has_no_gross_and_no_flag() -> None:
    result = calculate_flight_margin(_target_flight(data_cost="1.25"), as_of=date(2026, 10, 31))

    assert result.status is FlightStatus.NOT_STARTED
    assert result.volume_commitment is VolumeCommitment.TARGET
    assert (result.revenue, result.gross_revenue) == (None, None)
    assert (result.gross_differs_from_buyer_spend, result.data_cost_reported) == (False, False)


def test_a_committed_flight_ignores_the_reported_revenue_the_spend_and_has_no_gross() -> None:
    plain = calculate_flight_margin(_flight(), as_of=AFTER_AUGUST)
    with_reports = calculate_flight_margin(
        replace(_flight(), reported_revenue=Decimal("9.99"), buyer_spend=Decimal("123456.78")), as_of=AFTER_AUGUST
    )

    assert with_reports == plain
    assert plain.volume_commitment is VolumeCommitment.COMMITTED
    assert plain.revenue == Decimal("3631.01")
    assert plain.gross_revenue is None
    assert plain.gross_differs_from_buyer_spend is False


def test_a_running_committed_flight_is_still_pro_rated_whatever_is_reported() -> None:
    plain = calculate_flight_margin(_september_flight(), as_of=date(2026, 9, 10))
    with_reports = calculate_flight_margin(
        replace(_september_flight(), reported_revenue=Decimal("1.00"), buyer_spend=Decimal("2.00")),
        as_of=date(2026, 9, 10),
    )

    assert with_reports == plain
    assert plain.revenue == Decimal("500.00")


# --- The gross is compared with the buyer's spend; a data cost is flagged, never subtracted --------------------------

def test_a_gross_equal_to_the_spend_is_not_flagged() -> None:
    assert calculate_flight_margin(_target_flight(), as_of=AFTER_NOVEMBER).gross_differs_from_buyer_spend is False


def test_a_buyer_paying_above_the_cpm_is_flagged_and_every_amount_is_unchanged() -> None:
    plain = calculate_flight_margin(_target_flight(), as_of=AFTER_NOVEMBER)
    paying_more = calculate_flight_margin(_target_flight(buyer_spend="6050.00"), as_of=AFTER_NOVEMBER)

    assert paying_more.gross_differs_from_buyer_spend is True
    assert paying_more == replace(plain, gross_differs_from_buyer_spend=True)


@pytest.mark.parametrize(
    ("delivered_impressions", "gross", "flagged"),
    [
        (1_010_000, "5050.00", False),
        (1_010_002, "5050.01", True),
        (990_000, "4950.00", False),
        (989_998, "4949.99", True),
    ],
    ids=["one-percent-above", "a-cent-beyond-above", "one-percent-below", "a-cent-beyond-below"],
)
def test_exactly_one_percent_of_the_spend_is_inside_the_tolerance(
    delivered_impressions: int, gross: str, flagged: bool
) -> None:
    flight = _target_flight(delivered_impressions=delivered_impressions, buyer_spend="5000.00")

    result = calculate_flight_margin(flight, as_of=AFTER_NOVEMBER)

    assert result.gross_revenue == Decimal(gross)
    assert result.gross_differs_from_buyer_spend is flagged


def test_the_tolerance_is_one_hundredth_of_the_spend() -> None:
    assert flight_margin.GROSS_TOLERANCE == Decimal("0.01")


def test_a_gross_with_no_spend_is_flagged() -> None:
    result = calculate_flight_margin(_target_flight(buyer_spend="0"), as_of=AFTER_NOVEMBER)

    assert result.gross_differs_from_buyer_spend is True


@pytest.mark.parametrize("commitment", list(VolumeCommitment))
def test_a_data_cost_is_flagged_and_not_subtracted(commitment: VolumeCommitment) -> None:
    plain = calculate_flight_margin(_target_flight(volume_commitment=commitment), as_of=AFTER_NOVEMBER)
    with_data = calculate_flight_margin(
        _target_flight(volume_commitment=commitment, data_cost="1.25"), as_of=AFTER_NOVEMBER
    )

    assert with_data.data_cost_reported is True
    assert plain.data_cost_reported is False
    assert with_data == replace(plain, data_cost_reported=True)


@pytest.mark.parametrize("field", ["reported_revenue", "buyer_spend", "data_cost"])
def test_a_float_reported_amount_is_refused(field: str) -> None:
    with pytest.raises(TypeError, match=field):
        replace(_target_flight(), **{field: 1.5})  # type: ignore[arg-type]


# --- The base of the rebate: the sale of a committed flight, the served gross of a target one ------------------------

def _facts(volume_commitment: VolumeCommitment, delivered_impressions: int) -> FlightFacts:
    return flight_facts(
        flight_id=1, campaign_line_id=1, campaign_id=1, flight_start=NOVEMBER_START, flight_end=NOVEMBER_END,
        group_id=1, agency_id=1, campaign_type_id=1, channel="Any", channel_id=1, scope="national",
        contracted_impressions=1_000_000, sale_cpm=Decimal("5.00"), delivered_impressions=delivered_impressions,
        media_cost=Decimal(0), volume_commitment=volume_commitment, reported_revenue=Decimal("4400.00"),
        buyer_spend=Decimal("5500.00"),
    )


def test_the_rebate_base_of_a_committed_flight_is_its_contracted_revenue() -> None:
    assert rebate_base(_facts(VolumeCommitment.COMMITTED, 1_100_000)) == Decimal("5000.00")


def test_the_rebate_base_of_a_target_flight_is_its_served_gross() -> None:
    assert rebate_base(_facts(VolumeCommitment.TARGET, 1_100_000)) == Decimal("5500.00")
    assert rebate_base(_facts(VolumeCommitment.TARGET, 0)) == Decimal("0.00")


# --- A target flight's gross is always what was served at the CPM: a closed one is read from its snapshot -----------

def test_the_flight_input_takes_no_gross() -> None:
    assert "gross_revenue" not in {field.name for field in fields(FlightEconomics)}


def test_a_target_flight_s_gross_is_always_its_served_impressions_at_the_cpm() -> None:
    # 1,200,000 served at 5.00 € is a gross of 6,000.00 €, and the flag compares it with the spend.
    result = calculate_flight_margin(_target_flight(delivered_impressions=1_200_000), as_of=AFTER_NOVEMBER)

    assert result.gross_revenue == Decimal("6000.00")
    assert result.platform_cost == Decimal("1200.00")
    assert result.gross_differs_from_buyer_spend is True  # 6,000.00 against a spend of 5,500.00


def test_a_target_flight_s_gross_within_one_percent_of_the_spend_is_not_flagged() -> None:
    result = calculate_flight_margin(_target_flight(buyer_spend="6050.00", delivered_impressions=1_200_000), AFTER_NOVEMBER)

    assert (result.gross_revenue, result.gross_differs_from_buyer_spend) == (Decimal("6000.00"), False)
