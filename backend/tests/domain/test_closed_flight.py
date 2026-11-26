"""The snapshot of a closed flight: what the closing froze, read back without computing anything (finance/rebate-accrual).

The snapshot copies the amounts of the flight as the closing priced it and the delivery they were computed on. The
worked examples are those of `test_flight_margin.py`: the committed flight of 726,202 impressions at 5.00 € (margin
823.26 €), the target flight with a gross of 5,500.00 € (margin 2,750.00 €) and the DOOH flight of 280,000.5000 OTS
over 12,000 impressions.
"""

import ast
import dataclasses
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.services import closed_flight
from app.domain.services.closed_flight import (
    DELIVERED_CHANGE_TOLERANCE, MARGIN_CHANGE_TOLERANCE, check_closed_delivery, margin_from_snapshot, snapshot_of,
)
from app.domain.services.flight_margin import calculate_flight_margin
from app.domain.services.priced_flights import price_flights
from app.domain.value_objects.closed_flight import ClosedDeliveryCheck, ClosedFlightSnapshot
from app.domain.value_objects.margin import FlightEconomics, FlightStatus, WindowDelivery
from app.domain.value_objects.platform_rate import PlatformRateLevel, ResolvedPlatformRate
from app.domain.value_objects.priced_flight import FlightFacts, PlatformRates, PricedFlight
from app.domain.value_objects.rebate import Bracket, CounterKey, FlightRebate, LadderStep, RebateSchedule
from app.domain.value_objects.volume_commitment import VolumeCommitment
from tests.fixtures.flight_inputs import flight_facts

GROUP = 10
AGENCY = 20
SYSTEM_RATE = Decimal("1.00")
AUGUST_START = date(2026, 8, 1)
AUGUST_END = date(2026, 8, 31)
CLOSING_OF_AUGUST = date(2026, 9, 5)
NOVEMBER_START = date(2026, 11, 1)
NOVEMBER_END = date(2026, 11, 30)
CLOSING_OF_NOVEMBER = date(2026, 12, 1)


def _schedule(rate: str, scope: str = "national") -> RebateSchedule:
    return RebateSchedule(1, GROUP, None, "Directo", scope, date(2026, 1, 1), None, (Bracket(Decimal(0), None, Decimal(rate)),))


def _facts(**overrides: object) -> FlightFacts:
    values: dict[str, object] = {
        "flight_id": 1, "campaign_line_id": 100, "campaign_id": 1, "flight_start": AUGUST_START,
        "flight_end": AUGUST_END, "group_id": GROUP, "agency_id": AGENCY, "campaign_type_id": 7,
        "channel": "Directo", "channel_id": 3, "scope": "national", "contracted_impressions": 726_202,
        "sale_cpm": Decimal("5.00"), "delivered_impressions": 700_000, "media_cost": Decimal("1200.004"),
    }
    values.update(overrides)
    return flight_facts(**values)  # type: ignore[arg-type]


def _priced(facts: FlightFacts, schedules: list[RebateSchedule], as_of: date) -> PricedFlight:
    (priced,) = price_flights(schedules, PlatformRates(system=SYSTEM_RATE), [facts], as_of)
    return priced


def committed_flight() -> PricedFlight:
    # 25 % of 3,631.01 € is a rebate of 907.7525 €; the media cost is stored with more decimals than a cent.
    return _priced(_facts(data_cost=Decimal("0.75")), [_schedule("0.25")], CLOSING_OF_AUGUST)


def target_flight() -> PricedFlight:
    # 1,100,000 served at 5.00 € is a gross of 5,500.00 €; 10 % of it is 550.00 €.
    facts = _facts(
        flight_start=NOVEMBER_START, flight_end=NOVEMBER_END, contracted_impressions=1_000_000,
        delivered_impressions=1_100_000, media_cost=Decimal(0), volume_commitment=VolumeCommitment.TARGET,
        reported_revenue=Decimal("4400.00"), buyer_spend=Decimal("5500.00"),
    )
    return _priced(facts, [_schedule("0.10")], CLOSING_OF_NOVEMBER)


def dooh_flight() -> PricedFlight:
    # 300,000 OTS contracted at 5.00 €; 280,000.5000 OTS delivered over 12,000 real impressions; no schedule.
    facts = _facts(
        contracted_impressions=300_000, delivered_impressions=12_000, media_cost=Decimal(0),
        delivery_metric="ots", delivered=Decimal("280000.5000"),
    )
    return _priced(facts, [], CLOSING_OF_AUGUST)


def zero_sale_flight() -> PricedFlight:
    return _priced(_facts(sale_cpm=Decimal("0.00")), [_schedule("0.25")], CLOSING_OF_AUGUST)


def _snapshot(**overrides: object) -> ClosedFlightSnapshot:
    return dataclasses.replace(snapshot_of(committed_flight()), **overrides)  # type: ignore[arg-type]


# --- snapshot_of ---------------------------------------------------------------------------------------------------


def test_the_snapshot_of_a_committed_flight_copies_its_amounts_its_delivery_and_its_line() -> None:
    snapshot = snapshot_of(committed_flight())

    assert snapshot == ClosedFlightSnapshot(
        revenue=Decimal("3631.01"),
        contracted_revenue=Decimal("3631.01"),
        media_cost=Decimal("1200.00"),
        rebate=Decimal("907.75"),
        platform_cost=Decimal("700.00"),
        margin=Decimal("823.26"),
        gross_revenue=None,
        delivered_impressions=700_000,
        delivered=Decimal(700_000),
        window_media_cost=Decimal("1200.004"),
        window_reported_revenue=Decimal(0),
        window_buyer_spend=Decimal(0),
        window_data_cost=Decimal("0.75"),
        gross_differs_from_buyer_spend=False,
        data_cost_reported=True,
        delivery_metric="impressions",
        sale_cpm=Decimal("5.00"),
        contracted_impressions=726_202,
        volume_commitment=VolumeCommitment.COMMITTED,
    )


def test_the_snapshot_of_the_worked_target_flight_holds_its_gross_and_what_its_dsp_reported() -> None:
    snapshot = snapshot_of(target_flight())

    assert (snapshot.gross_revenue, snapshot.revenue, snapshot.rebate, snapshot.platform_cost, snapshot.margin) == (
        Decimal("5500.00"), Decimal("4400.00"), Decimal("550.00"), Decimal("1100.00"), Decimal("2750.00"),
    )
    assert snapshot.contracted_revenue == Decimal("5000.00")
    assert (snapshot.window_reported_revenue, snapshot.window_buyer_spend) == (Decimal("4400.00"), Decimal("5500.00"))
    assert (snapshot.delivered_impressions, snapshot.delivered) == (1_100_000, Decimal(1_100_000))
    assert snapshot.volume_commitment is VolumeCommitment.TARGET
    assert snapshot.gross_differs_from_buyer_spend is False


def test_the_snapshot_of_a_dooh_flight_holds_its_ots_and_its_real_impressions() -> None:
    snapshot = snapshot_of(dooh_flight())

    assert (snapshot.delivered, snapshot.delivered_impressions, snapshot.delivery_metric) == (
        Decimal("280000.5000"), 12_000, "ots",
    )
    assert (snapshot.contracted_impressions, snapshot.revenue, snapshot.rebate) == (
        300_000, Decimal("1500.00"), Decimal("0.00"),
    )
    assert (snapshot.platform_cost, snapshot.margin) == (Decimal("12.00"), Decimal("1488.00"))


# The closing freezes the flights ending on or before its `as_of` (`open_ended_flights`), and prices them with
# `price_flights` at that same `as_of`: a flight ending on it is closed, one ending the next day is still running.


def test_a_flight_ending_on_the_closing_s_as_of_has_a_snapshot() -> None:
    last_day = _priced(_facts(), [_schedule("0.25")], AUGUST_END)

    assert snapshot_of(last_day).margin == Decimal("823.26")


def test_a_running_flight_has_no_snapshot() -> None:
    running = _priced(_facts(), [_schedule("0.25")], AUGUST_END - timedelta(days=1))

    assert running.margin.status is FlightStatus.RUNNING
    with pytest.raises(ValueError, match="not closed"):
        snapshot_of(running)


def test_a_flight_that_has_not_started_has_no_snapshot() -> None:
    # `price_flights` leaves it out; built here to prove the rule does not depend on that.
    closed = committed_flight()
    not_started = dataclasses.replace(
        closed, margin=calculate_flight_margin(_economics_at_closing(VolumeCommitment.COMMITTED), date(2026, 7, 31)),
    )

    assert not_started.margin.status is FlightStatus.NOT_STARTED
    with pytest.raises(ValueError, match="not closed"):
        snapshot_of(not_started)


# --- ClosedFlightSnapshot ------------------------------------------------------------------------------------------


def test_a_committed_snapshot_with_a_gross_is_refused() -> None:
    with pytest.raises(ValueError, match="gross"):
        _snapshot(gross_revenue=Decimal("3631.01"))


def test_a_target_snapshot_without_a_gross_is_refused() -> None:
    with pytest.raises(ValueError, match="gross"):
        _snapshot(volume_commitment=VolumeCommitment.TARGET)


@pytest.mark.parametrize(
    "name",
    [
        "revenue", "contracted_revenue", "media_cost", "rebate", "platform_cost", "margin", "delivered",
        "window_media_cost", "window_reported_revenue", "window_buyer_spend", "window_data_cost", "sale_cpm",
    ],
)
def test_an_amount_that_is_not_a_decimal_is_refused(name: str) -> None:
    with pytest.raises(TypeError, match=name):
        _snapshot(**{name: 1.5})


def test_a_target_gross_that_is_not_a_decimal_is_refused() -> None:
    with pytest.raises(TypeError, match="gross_revenue"):
        dataclasses.replace(snapshot_of(target_flight()), gross_revenue=5500.0)  # type: ignore[arg-type]


# --- margin_from_snapshot ------------------------------------------------------------------------------------------


def test_a_closed_flight_read_from_its_snapshot_carries_every_figure_of_the_snapshot() -> None:
    snapshot = snapshot_of(committed_flight())

    margin = margin_from_snapshot(snapshot, AUGUST_START, AUGUST_END)

    assert margin.status is FlightStatus.CLOSED
    assert margin.provisional is False
    assert (margin.accrued_days, margin.window_days) == (31, 31)
    assert (margin.revenue, margin.contracted_revenue, margin.media_cost, margin.rebate, margin.platform_cost) == (
        Decimal("3631.01"), Decimal("3631.01"), Decimal("1200.00"), Decimal("907.75"), Decimal("700.00"),
    )
    assert margin.margin == Decimal("823.26")
    assert margin.margin_pct == Decimal("22.67")
    assert (margin.delivered_impressions, margin.contracted_impressions, margin.delivered, margin.delivery_metric) == (
        700_000, 726_202, Decimal(700_000), "impressions",
    )
    assert margin.volume_commitment is VolumeCommitment.COMMITTED
    assert margin.gross_revenue is None
    assert (margin.below_cost, margin.zero_sale) == (False, False)
    assert (margin.gross_differs_from_buyer_spend, margin.data_cost_reported) == (False, True)


def test_the_figures_are_the_snapshot_s_and_are_never_computed_again() -> None:
    # A snapshot whose amounts do not add up is read as it is: the margin is the frozen one, not revenue minus costs.
    snapshot = _snapshot(margin=Decimal("-0.01"), platform_cost=Decimal("123.45"))

    margin = margin_from_snapshot(snapshot, AUGUST_START, AUGUST_END)

    assert (margin.margin, margin.platform_cost, margin.revenue) == (
        Decimal("-0.01"), Decimal("123.45"), Decimal("3631.01"),
    )
    assert margin.below_cost is True
    assert margin.margin_pct == Decimal("0.00")


def test_zero_sale_comes_from_the_frozen_sale_cpm() -> None:
    assert margin_from_snapshot(_snapshot(sale_cpm=Decimal("0.00")), AUGUST_START, AUGUST_END).zero_sale is True


def test_the_flags_of_a_target_flight_come_from_the_snapshot() -> None:
    snapshot = dataclasses.replace(
        snapshot_of(target_flight()), gross_differs_from_buyer_spend=True, data_cost_reported=True
    )

    margin = margin_from_snapshot(snapshot, NOVEMBER_START, NOVEMBER_END)

    assert margin.gross_revenue == Decimal("5500.00")
    assert margin.volume_commitment is VolumeCommitment.TARGET
    assert (margin.gross_differs_from_buyer_spend, margin.data_cost_reported) == (True, True)
    assert (margin.accrued_days, margin.window_days) == (30, 30)


@pytest.mark.parametrize("priced", [committed_flight(), target_flight(), zero_sale_flight(), dooh_flight()])
def test_a_flight_read_from_its_snapshot_is_the_flight_its_closing_priced(priced: PricedFlight) -> None:
    snapshot = snapshot_of(priced)

    assert margin_from_snapshot(snapshot, priced.facts.flight_start, priced.facts.flight_end) == priced.margin


def _economics_at_closing(commitment: VolumeCommitment) -> FlightEconomics:
    # Amounts with more decimals than a cent, a rate that is not 1.00 € and both flags raised on the target flight.
    return FlightEconomics(
        flight_start=AUGUST_START, flight_end=AUGUST_END, contracted_impressions=726_202, sale_cpm=Decimal("4.37"),
        delivered_impressions=812_345, media_cost=Decimal("1534.567891"), rebate_amount=Decimal("473.218765432109"),
        platform_rate=Decimal("1.37"), delivery_metric="impressions", delivered=Decimal(812_345),
        volume_commitment=commitment, reported_revenue=Decimal("3412.344999"), buyer_spend=Decimal("2999.99"),
        data_cost=Decimal("0.000001"),
    )


def _priced_from(economics: FlightEconomics, as_of: date) -> PricedFlight:
    """The flight as the closing priced it: the margin is `calculate_flight_margin` on these very economics."""
    facts = _facts(
        flight_start=economics.flight_start, flight_end=economics.flight_end,
        contracted_impressions=economics.contracted_impressions, sale_cpm=economics.sale_cpm,
        delivered_impressions=economics.delivered_impressions, media_cost=economics.media_cost,
        delivery_metric=economics.delivery_metric, delivered=economics.delivered,
        volume_commitment=economics.volume_commitment, reported_revenue=economics.reported_revenue,
        buyer_spend=economics.buyer_spend, data_cost=economics.data_cost,
    )
    rebate = FlightRebate(
        flight_id=1, counter=CounterKey(GROUP, None, "Directo", 2026), step=LadderStep.GROUP_CHANNEL_SCOPE,
        agency_exception=False, source_year=None, zero_reason=None, schedule_id=1, effective_rate=Decimal("0.15"),
        position_before=Decimal(0), position_after=Decimal(0), charges=(), rebate=economics.rebate_amount,
    )
    platform = ResolvedPlatformRate(economics.platform_rate, PlatformRateLevel.LINE)
    return PricedFlight(facts, rebate, platform, calculate_flight_margin(economics, as_of))


@pytest.mark.parametrize("commitment", [VolumeCommitment.COMMITTED, VolumeCommitment.TARGET])
def test_the_margin_read_from_a_snapshot_is_the_margin_calculate_flight_margin_gave_at_the_closing(
    commitment: VolumeCommitment,
) -> None:
    economics = _economics_at_closing(commitment)
    at_closing = calculate_flight_margin(economics, CLOSING_OF_AUGUST)

    read = margin_from_snapshot(
        snapshot_of(_priced_from(economics, CLOSING_OF_AUGUST)), economics.flight_start, economics.flight_end
    )

    assert at_closing.status is FlightStatus.CLOSED
    assert read == at_closing
    assert read.margin_pct == at_closing.margin_pct
    if commitment is VolumeCommitment.TARGET:
        assert (read.gross_differs_from_buyer_spend, read.data_cost_reported) == (True, True)


def test_the_margin_of_a_closed_flight_is_never_computed() -> None:
    # The module never imports the margin formula, and the read calls nothing that rounds: it only copies.
    tree = ast.parse(Path(closed_flight.__file__).read_text())
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
    (read,) = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "margin_from_snapshot"]
    called = {node.func.id for node in ast.walk(read) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}

    assert "calculate_flight_margin" not in imported
    assert called == {"FlightMargin"}


# --- check_closed_delivery (finance/margin-calculation, «A closed flight is checked against its current delivery») ---
#
# The committed flight of the example closed with a revenue of 5,000.00 € (1,000,000 at 5.00 €), a media cost of
# 1,200.00 €, a rebate of 1,250.00 €, a platform cost of 700.00 € on 700,000 impressions at 1.00 € and a margin of
# 1,850.00 €. The Deal flight is the worked target example of the snapshot above.

FROZEN_RATE = Decimal("1.00")


def _closed_committed(**overrides: object) -> ClosedFlightSnapshot:
    values: dict[str, object] = {
        "revenue": Decimal("5000.00"), "contracted_revenue": Decimal("5000.00"), "media_cost": Decimal("1200.00"),
        "rebate": Decimal("1250.00"), "platform_cost": Decimal("700.00"), "margin": Decimal("1850.00"),
        "gross_revenue": None, "delivered_impressions": 700_000, "delivered": Decimal("700000.0000"),
        "window_media_cost": Decimal("1200.000000"), "window_reported_revenue": Decimal(0),
        "window_buyer_spend": Decimal(0), "window_data_cost": Decimal(0), "gross_differs_from_buyer_spend": False,
        "data_cost_reported": False, "delivery_metric": "impressions", "sale_cpm": Decimal("5.00"),
        "contracted_impressions": 1_000_000, "volume_commitment": VolumeCommitment.COMMITTED,
    }
    values.update(overrides)
    return ClosedFlightSnapshot(**values)  # type: ignore[arg-type]


def _closed_dooh() -> ClosedFlightSnapshot:
    # 300,000.0000 OTS over 12,000 impressions: revenue 1,500.00 €, platform cost 12.00 €, margin 1,488.00 €.
    return _closed_committed(
        revenue=Decimal("1500.00"), contracted_revenue=Decimal("1500.00"), media_cost=Decimal("0.00"),
        rebate=Decimal("0.00"), platform_cost=Decimal("12.00"), margin=Decimal("1488.00"),
        delivered_impressions=12_000, delivered=Decimal("300000.0000"), window_media_cost=Decimal(0),
        delivery_metric="ots", contracted_impressions=300_000,
    )


def _delivery_of(snapshot: ClosedFlightSnapshot, **changes: object) -> WindowDelivery:
    """The delivery the snapshot was closed with, with some of it changed."""
    values: dict[str, object] = {
        "impressions": snapshot.delivered_impressions, "media_cost": snapshot.window_media_cost,
        "delivered": snapshot.delivered, "reported_revenue": snapshot.window_reported_revenue,
        "buyer_spend": snapshot.window_buyer_spend, "data_cost": snapshot.window_data_cost,
    }
    values.update(changes)
    return WindowDelivery(**values)  # type: ignore[arg-type]


def test_the_tolerances_are_one_euro_of_margin_and_one_percent_of_volume() -> None:
    assert MARGIN_CHANGE_TOLERANCE == Decimal("1.00")
    assert DELIVERED_CHANGE_TOLERANCE == Decimal("0.01")


def test_the_restated_committed_flight_of_the_example_is_flagged() -> None:
    snapshot = _closed_committed()
    current = _delivery_of(
        snapshot, impressions=1_200_000, delivered=Decimal("1200000.0000"), media_cost=Decimal("3000.000000"),
    )

    check = check_closed_delivery(snapshot, FROZEN_RATE, current)

    assert check == ClosedDeliveryCheck(
        delivered_difference=Decimal("500000.0000"),
        delivered_impressions_difference=500_000,
        media_cost_difference=Decimal("1800.00"),
        reported_revenue_difference=None,
        buyer_spend_difference=None,
        current_margin=Decimal("-450.00"),
        margin_difference=Decimal("-2300.00"),
        changed=True,
    )
    assert snapshot.margin == Decimal("1850.00")


def test_a_delivery_equal_to_the_frozen_one_raises_nothing() -> None:
    snapshot = _closed_committed()

    check = check_closed_delivery(snapshot, FROZEN_RATE, _delivery_of(snapshot))

    assert check == ClosedDeliveryCheck(
        delivered_difference=Decimal("0.0000"), delivered_impressions_difference=0,
        media_cost_difference=Decimal("0.00"), reported_revenue_difference=None, buyer_spend_difference=None,
        current_margin=Decimal("1850.00"), margin_difference=Decimal("0.00"), changed=False,
    )


@pytest.mark.parametrize(
    ("media_cost", "changed"),
    [("1200.99", False), ("1201.00", True), ("1199.01", False), ("1199.00", True)],
)
def test_a_margin_difference_of_one_euro_is_flagged_and_of_99_cents_is_not(media_cost: str, changed: bool) -> None:
    snapshot = _closed_committed()

    check = check_closed_delivery(snapshot, FROZEN_RATE, _delivery_of(snapshot, media_cost=Decimal(media_cost)))

    assert abs(check.margin_difference) == abs(Decimal(media_cost) - Decimal("1200.00"))
    assert check.changed is changed


def test_the_media_cost_is_rounded_before_it_is_subtracted() -> None:
    snapshot = _closed_committed(window_media_cost=Decimal("1200.004"))

    check = check_closed_delivery(snapshot, FROZEN_RATE, _delivery_of(snapshot, media_cost=Decimal("1200.005")))

    assert check.media_cost_difference == Decimal("0.01")
    assert check.current_margin == Decimal("1849.99")


@pytest.mark.parametrize(
    ("delivered", "changed"),
    [("303000.0000", True), ("302999.9999", False), ("297000.0000", True), ("297000.0001", False)],
)
def test_a_delivered_volume_one_percent_away_is_flagged(delivered: str, changed: bool) -> None:
    snapshot = _closed_dooh()

    check = check_closed_delivery(snapshot, FROZEN_RATE, _delivery_of(snapshot, delivered=Decimal(delivered)))

    assert check.margin_difference == Decimal("0.00")
    assert check.delivered_difference == Decimal(delivered) - Decimal("300000.0000")
    assert check.changed is changed


def test_delivery_appearing_after_a_closing_with_none_is_flagged() -> None:
    snapshot = _closed_committed(
        media_cost=Decimal("0.00"), platform_cost=Decimal("0.00"), margin=Decimal("3750.00"),
        delivered_impressions=0, delivered=Decimal("0.0000"), window_media_cost=Decimal(0),
    )

    check = check_closed_delivery(snapshot, FROZEN_RATE, _delivery_of(snapshot, impressions=10, delivered=Decimal(10)))

    assert check.margin_difference == Decimal("-0.01")  # 10 impressions at 1.00 € per thousand
    assert check.changed is True


def test_a_closing_with_no_delivery_still_without_delivery_is_not_flagged() -> None:
    snapshot = _closed_committed(
        media_cost=Decimal("0.00"), platform_cost=Decimal("0.00"), margin=Decimal("3750.00"),
        delivered_impressions=0, delivered=Decimal("0.0000"), window_media_cost=Decimal(0),
    )

    assert check_closed_delivery(snapshot, FROZEN_RATE, _delivery_of(snapshot)).changed is False


def test_a_restated_target_flight_keeps_the_closing_s_rebate_in_its_current_margin() -> None:
    snapshot = snapshot_of(target_flight())
    current = _delivery_of(
        snapshot, impressions=1_300_000, delivered=Decimal(1_300_000), reported_revenue=Decimal("5200.00"),
        buyer_spend=Decimal("6500.00"),
    )

    check = check_closed_delivery(snapshot, FROZEN_RATE, current)

    assert check == ClosedDeliveryCheck(
        delivered_difference=Decimal("200000.0000"),
        delivered_impressions_difference=200_000,
        media_cost_difference=Decimal("0.00"),
        reported_revenue_difference=Decimal("800.00"),
        buyer_spend_difference=Decimal("1000.00"),
        current_margin=Decimal("3350.00"),
        margin_difference=Decimal("600.00"),
        changed=True,
    )
    assert (snapshot.revenue, snapshot.gross_revenue, snapshot.rebate, snapshot.margin) == (
        Decimal("4400.00"), Decimal("5500.00"), Decimal("550.00"), Decimal("2750.00"),
    )


def test_the_reported_revenue_and_spend_of_a_target_flight_are_rounded_before_they_are_subtracted() -> None:
    snapshot = dataclasses.replace(
        snapshot_of(target_flight()), window_reported_revenue=Decimal("4400.004"), window_buyer_spend=Decimal("5499.996"),
    )
    current = _delivery_of(snapshot, reported_revenue=Decimal("4400.005"), buyer_spend=Decimal("5500.004"))

    check = check_closed_delivery(snapshot, FROZEN_RATE, current)

    assert (check.reported_revenue_difference, check.buyer_spend_difference) == (Decimal("0.01"), Decimal("0.00"))
    assert check.current_margin == Decimal("2750.01")


def test_a_committed_flight_reports_no_revenue_or_spend_difference_and_keeps_its_frozen_revenue() -> None:
    snapshot = _closed_committed()
    current = _delivery_of(snapshot, reported_revenue=Decimal("9999.00"), buyer_spend=Decimal("8888.00"))

    check = check_closed_delivery(snapshot, FROZEN_RATE, current)

    assert (check.reported_revenue_difference, check.buyer_spend_difference) == (None, None)
    assert check.current_margin == Decimal("1850.00")
    assert check.changed is False


def test_the_current_platform_cost_uses_the_frozen_rate_given() -> None:
    snapshot = _closed_committed(platform_cost=Decimal("959.00"), margin=Decimal("1591.00"))

    check = check_closed_delivery(snapshot, Decimal("1.37"), _delivery_of(snapshot, impressions=700_001))

    # 700,001 / 1000 × 1.37 = 959.00137, rounded 959.00: only the impressions moved, by one.
    assert check.current_margin == Decimal("1591.00")
    assert (check.delivered_impressions_difference, check.changed) == (1, False)
