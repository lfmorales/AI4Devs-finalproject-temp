"""Acceptance of a month still running: the domain against the private sheet, row by row and in aggregate.

`margin_pct_actual` is the column compared: it accrues revenue and rebate by days served over days of the purchase
order and subtracts the costs of what was served. `margin_pct_full_month` is not replicated (it subtracts partial
costs from the sale of the whole month); that is a known difference of the source sheet. Nothing here knows a figure
of the sheet. A row that does not match is reported with its numbers, never fixed by touching the code.
"""

from decimal import Decimal

import pytest

from app.domain.services.margin_totals import total_flights
from app.domain.value_objects.margin import FlightStatus
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


def test_each_amount_of_each_row_matches_the_sheet(compared, priced):
    failures: list[str] = []
    for row in compared:
        margin = priced[row.number].margin
        checks = [
            ("revenue", margin.revenue, row.accrued_revenue, CENT),
            ("rebate", margin.rebate, row.accrued_rebate, CENT),
            ("media cost", margin.media_cost, row.purchase_cost, CENT),
            ("platform cost", margin.platform_cost, row.platform_cost, CENT),
            ("margin", margin.margin, row.expected_margin, MARGIN_TOLERANCE),
        ]
        failures += [_report(row, name, ours, sheet) for name, ours, sheet, tol in checks if abs(ours - sheet) > tol]
    assert not failures, "\n".join(failures)


def test_each_margin_percentage_matches_the_actual_one_of_the_sheet(compared, priced):
    failures: list[str] = []
    for row in compared:
        ours = priced[row.number].margin.margin_pct
        assert row.margin_pct_actual is not None, row.campaign
        sheet = row.margin_pct_actual * HUNDRED
        if ours is None or abs(ours - sheet) > PCT_TOLERANCE:
            failures.append(_report(row, "margin_pct", ours, sheet))
    assert not failures, "\n".join(failures)


def test_a_row_is_below_cost_exactly_when_the_sheet_percentage_is_negative(compared, priced):
    ours = {row.number for row in compared if priced[row.number].margin.below_cost}
    sheet = {row.number for row in compared if row.margin_pct_actual < 0}

    assert ours == sheet, f"ours only: {sorted(ours - sheet)}, sheet only: {sorted(sheet - ours)}"


# ---------------------------------------------------------------- aggregate over the compared rows

@pytest.fixture(scope="module")
def totals(compared, priced):
    return total_flights(priced[row.number].margin for row in compared)


def _sum(compared, attribute) -> Decimal:
    return sum((attribute(row) for row in compared), Decimal(0))


def test_the_accrued_revenue_matches_the_sheet(compared, totals):
    sheet = _sum(compared, lambda row: row.accrued_revenue)

    assert abs(totals.revenue - sheet) <= AGGREGATE_TOLERANCE, f"ours={totals.revenue} sheet={sheet}"


def test_the_provisional_margin_matches_the_sheet(compared, totals):
    sheet = _sum(compared, lambda row: row.expected_margin)

    assert abs(totals.margin - sheet) <= AGGREGATE_TOLERANCE, f"ours={totals.margin} sheet={sheet}"
    assert totals.provisional is True


def test_the_percentage_on_the_accrued_revenue_matches_the_sheet(compared, totals):
    sheet = _sum(compared, lambda row: row.expected_margin) / _sum(compared, lambda row: row.accrued_revenue) * HUNDRED

    assert abs(totals.margin_pct - sheet) <= AGGREGATE_PCT_TOLERANCE, f"ours={totals.margin_pct} sheet={sheet}"


def test_the_number_of_negative_margin_flights_matches_the_sheet(compared, totals):
    assert totals.below_cost_count == sum(1 for row in compared if row.margin_pct_actual < 0)
