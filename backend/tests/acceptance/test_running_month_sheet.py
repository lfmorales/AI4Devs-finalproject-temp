"""Acceptance of a month still running: the domain against the private sheet, row by row and in aggregate.

`margin_pct_actual` is the column compared: it accrues revenue and rebate by days served over days of the purchase
order and subtracts the costs of what was served. `margin_pct_full_month` is not replicated (it subtracts partial
costs from the sale of the whole month); that is a known difference of the source sheet. Nothing here knows a figure
of the sheet. A row that does not match is reported with its numbers, never fixed by touching the code.

Known difference with the sheet (committed-billing-and-review, confirmed by the business on 2026-11-26). The sheet
accrues each row's sale and rebate by days served over days of the purchase order; a committed flight now earns its
billing to date, the lesser of served and contracted, with no pro-rating of the revenue or the rebate. The expected
figures are the sheet's own columns with that rule applied (`expected_revenue`, `expected_rebate`, `expected_margin` in
running_month_sheet.py). The rows that depart from the sheet are the running ones, and among the closed ones exactly
those that served less than they contracted (Campaign 18 on the sheet of 2026-11-26); the closed rows that served their
volume still match the sheet. Over the 35 rows compared, the revenue to date is 17,847.17 € below the sheet's accrual
and the margin 11,906.44 € below it, nearly all of it in the 23 running rows. The tests under «the known difference
with the sheet» check it and record the aggregate difference with `record_property`.
"""

from collections.abc import Callable
from decimal import Decimal

import pytest

from app.domain.services.margin_totals import total_flights
from app.domain.value_objects.margin import FlightStatus, MarginTotals
from app.domain.value_objects.priced_flight import PricedFlight
from tests.acceptance.running_month_sheet import (
    MANUAL_ADJUSTMENT_REASON,
    MANUAL_ADJUSTMENT_ROW,
    NO_VOLUME_REASON,
    SHEET_PATH,
    SKIP_REASON,
    SheetRow,
    load_rows,
    price_row,
    split_rows,
)

pytestmark = pytest.mark.skipif(not SHEET_PATH.exists(), reason=SKIP_REASON)

CENT = Decimal("0.01")
MARGIN_TOLERANCE = Decimal("0.04")
PCT_TOLERANCE = Decimal("0.05")
AGGREGATE_TOLERANCE = Decimal(1)
AGGREGATE_PCT_TOLERANCE = Decimal("0.1")
HUNDRED = Decimal(100)


@pytest.fixture(scope="module")
def rows() -> list[SheetRow]:
    return load_rows()


@pytest.fixture(scope="module")
def compared(rows) -> list[SheetRow]:
    return split_rows(rows)[0]


@pytest.fixture(scope="module")
def priced(compared):
    return {row.number: price_row(row) for row in compared}


def _report(row: SheetRow, name: str, ours: Decimal | None, sheet: Decimal) -> str:
    return (f"{row.campaign} (row {row.number}, {row.days_served}/{row.days_oc} days): {name} "
            f"ours={ours} sheet={sheet} difference={None if ours is None else ours - sheet}")


# ---------------------------------------------------------------- what is compared

def test_the_rows_left_out_are_exactly_those_with_no_volume_and_the_manually_adjusted_one(rows):
    compared, no_volume, adjusted = split_rows(rows)

    assert {row.number for row in no_volume} == {row.number for row in rows if row.oc_impressions == 0}
    assert [row.campaign for row in adjusted] == [MANUAL_ADJUSTMENT_ROW]
    assert not {r.number for r in compared} & ({r.number for r in no_volume} | {r.number for r in adjusted})
    assert {r.number for r in compared} | {r.number for r in no_volume} | {r.number for r in adjusted} == {r.number for r in rows}
    assert all(row.oc_impressions > 0 and row.days_oc for row in compared)
    assert "sin volumen contratado" in NO_VOLUME_REASON and "ajuste manual" in MANUAL_ADJUSTMENT_REASON


def test_the_manual_adjustment_of_the_excluded_row_is_the_only_closed_row_whose_rebate_departs_from_its_rate(rows):
    compared, _, adjusted = split_rows(rows)
    closed = [row for row in compared if row.is_closed and row.rebate_rate is not None]

    # For a closed row the accrued rebate is the whole month's: the sheet's rebate cost must be its rate times its sale.
    assert closed and all(abs(row.rebate_cost - row.rebate_rate * row.sale) <= CENT for row in closed)
    (row,) = adjusted
    assert row.is_closed
    assert abs(row.rebate_cost - row.rebate_rate * row.sale) > CENT, "the row no longer carries a manual adjustment"
    print(f"\n[acceptance] {row.campaign}: rebate cost in the sheet {row.rebate_cost}, at its own rate "
          f"{row.rebate_rate * row.sale}; adjustment {row.rebate_cost - row.rebate_rate * row.sale}")


def test_the_cost_of_the_rows_without_volume_makes_the_difference_with_the_sheet_explicit(rows, record_property):
    compared, no_volume, adjusted = split_rows(rows)
    sheet_cost = sum((row.total_cost for row in rows), Decimal(0))
    left_out_cost = sum((row.total_cost for row in no_volume), Decimal(0))
    share = left_out_cost / sheet_cost * HUNDRED
    record_property("rows_without_volume", [row.campaign for row in no_volume])
    record_property("their_total_cost", str(left_out_cost))
    record_property("share_of_the_months_cost_percent", str(share))
    print(f"\n[acceptance] rows without volume: {len(no_volume)} ({NO_VOLUME_REASON}); their total cost: {left_out_cost}, "
          f"{share.quantize(CENT)} % of the month's cost ({sheet_cost}); Campaign 38 left out apart: {MANUAL_ADJUSTMENT_REASON}")

    assert left_out_cost == sum((row.total_cost for row in rows if row.oc_impressions == 0), Decimal(0))
    assert sheet_cost == sum((row.total_cost for row in compared), Decimal(0)) + left_out_cost + sum(
        (row.total_cost for row in adjusted), Decimal(0))
    assert Decimal(0) < share < HUNDRED


# ---------------------------------------------------------------- row by row

def test_every_state_is_provisional_when_running_and_closed_when_the_days_are_all_served(compared, priced):
    wrong = [
        f"{row.campaign}: expected {'closed' if row.is_closed else 'running'}, got {priced[row.number].margin.status.value}"
        for row in compared
        if priced[row.number].margin.status is not (FlightStatus.CLOSED if row.is_closed else FlightStatus.RUNNING)
        or priced[row.number].margin.provisional is row.is_closed
    ]
    assert not wrong, "\n".join(wrong)
    assert any(row.is_closed for row in compared) and any(not row.is_closed for row in compared)


def test_each_amount_of_each_row_matches_the_sheet_billed_to_date(compared, priced):
    failures: list[str] = []
    for row in compared:
        margin = priced[row.number].margin
        checks = [
            ("revenue", margin.revenue, row.expected_revenue, CENT),
            ("rebate", margin.rebate, row.expected_rebate, CENT),
            ("media cost", margin.media_cost, row.purchase_cost, CENT),
            ("platform cost", margin.platform_cost, row.platform_cost, CENT),
            ("margin", margin.margin, row.expected_margin, MARGIN_TOLERANCE),
        ]
        failures += [_report(row, name, ours, sheet) for name, ours, sheet, tol in checks if abs(ours - sheet) > tol]
    assert not failures, "\n".join(failures)


def test_each_margin_percentage_matches_the_sheet_billed_to_date(compared, priced):
    failures: list[str] = []
    for row in compared:
        ours = priced[row.number].margin.margin_pct
        if row.expected_revenue == 0:
            if ours is not None:
                failures.append(f"{row.campaign} (row {row.number}): margin_pct ours={ours}, no revenue to divide by")
            continue
        expected = row.expected_margin / row.expected_revenue * HUNDRED
        if ours is None or abs(ours - expected) > PCT_TOLERANCE:
            failures.append(_report(row, "margin_pct", ours, expected))
    assert not failures, "\n".join(failures)


def test_a_row_is_below_cost_exactly_when_its_expected_margin_is_negative(compared, priced):
    ours = {row.number for row in compared if priced[row.number].margin.below_cost}
    expected = {row.number for row in compared if row.expected_margin < 0}

    assert ours == expected, f"ours only: {sorted(ours - expected)}, expected only: {sorted(expected - ours)}"


# ---------------------------------------------------------------- the known difference with the sheet

def _departs(row: SheetRow) -> bool:
    return abs(row.expected_revenue - row.accrued_revenue) > CENT


def test_the_closed_rows_that_depart_from_the_sheet_are_exactly_those_that_served_less_than_they_contracted(
    compared: list[SheetRow], priced: dict[int, PricedFlight], record_property: Callable[[str, object], None]
) -> None:
    closed = [row for row in compared if row.is_closed]
    departing = [row for row in closed if _departs(row)]
    record_property("closed_rows_billed_below_the_sheet", [row.campaign for row in departing])
    print(f"\n[acceptance] closed rows billed below the sheet: {', '.join(row.campaign for row in departing)}")

    assert {row.number for row in departing} == {row.number for row in closed if row.served_less_than_contracted}
    # The closed rows that served their volume still match the sheet itself.
    failures: list[str] = []
    for row in closed:
        if row in departing:
            continue
        margin = priced[row.number].margin
        assert row.margin_pct_actual is not None, row.campaign
        for name, ours, sheet, tolerance in (
            ("revenue", margin.revenue, row.accrued_revenue, CENT),
            ("rebate", margin.rebate, row.accrued_rebate, CENT),
            ("margin", margin.margin, row.sheet_margin, MARGIN_TOLERANCE),
            ("margin_pct", margin.margin_pct, row.margin_pct_actual * HUNDRED, PCT_TOLERANCE),
        ):
            if ours is None or abs(ours - sheet) > tolerance:
                failures.append(_report(row, name, ours, sheet))
    assert not failures, "\n".join(failures)


def test_the_known_difference_with_the_sheet_s_accrual_is_recorded(
    compared: list[SheetRow], totals: MarginTotals, record_property: Callable[[str, object], None]
) -> None:
    running = [row for row in compared if not row.is_closed]
    revenue_difference = totals.revenue - _sum(compared, lambda row: row.accrued_revenue)
    margin_difference = totals.margin - _sum(compared, lambda row: row.sheet_margin)
    record_property("running_rows", len(running))
    record_property("revenue_difference", str(revenue_difference.quantize(CENT)))
    record_property("margin_difference", str(margin_difference.quantize(CENT)))
    print(f"\n[acceptance] against the sheet's accrual: {len(running)} running rows, revenue "
          f"{revenue_difference.quantize(CENT)}, margin {margin_difference.quantize(CENT)}")

    assert running
    assert revenue_difference.quantize(CENT) == _sum(
        compared, lambda row: row.expected_revenue - row.accrued_revenue
    ).quantize(CENT)
    assert revenue_difference < 0 and margin_difference < 0


# ---------------------------------------------------------------- aggregate over the compared rows

@pytest.fixture(scope="module")
def totals(compared, priced):
    return total_flights(priced[row.number].margin for row in compared)


def _sum(compared, attribute) -> Decimal:
    return sum((attribute(row) for row in compared), Decimal(0))


def test_the_revenue_to_date_matches_the_sheet_billed_to_date(compared, totals):
    expected = _sum(compared, lambda row: row.expected_revenue)

    assert abs(totals.revenue - expected) <= AGGREGATE_TOLERANCE, f"ours={totals.revenue} expected={expected}"


def test_the_provisional_margin_matches_the_sheet_billed_to_date(compared, totals):
    expected = _sum(compared, lambda row: row.expected_margin)

    assert abs(totals.margin - expected) <= AGGREGATE_TOLERANCE, f"ours={totals.margin} expected={expected}"
    assert totals.provisional is True


def test_the_percentage_on_the_revenue_to_date_matches_the_sheet_billed_to_date(compared, totals):
    expected = _sum(compared, lambda row: row.expected_margin) / _sum(compared, lambda row: row.expected_revenue) * HUNDRED

    assert abs(totals.margin_pct - expected) <= AGGREGATE_PCT_TOLERANCE, f"ours={totals.margin_pct} expected={expected}"


def test_the_number_of_negative_margin_flights_matches_the_sheet_billed_to_date(compared, totals):
    assert totals.below_cost_count == sum(1 for row in compared if row.expected_margin < 0)
