"""Acceptance of the closed month: the domain against the private sheet, row by row and in aggregate.

Nothing here knows a figure of the sheet: it reads the sheet and compares. A row that does not match is
reported with its numbers, never fixed by touching the code.
"""

from decimal import Decimal

import pytest

from app.domain.services.margin_totals import total_flights
from tests.acceptance.closed_month_sheet import (
    EXCLUDED_REASON,
    SHEET_PATH,
    SKIP_REASON,
    SheetRow,
    load_rows,
    price_rows,
    split_rows,
)

pytestmark = pytest.mark.skipif(not SHEET_PATH.exists(), reason=SKIP_REASON)

CENT = Decimal("0.01")
MARGIN_TOLERANCE = Decimal("0.04")
PCT_TOLERANCE = Decimal("0.05")          # percentage points, per row
AGGREGATE_TOLERANCE = Decimal(1)         # euros
AGGREGATE_PCT_TOLERANCE = Decimal("0.1")  # percentage points
HUNDRED = Decimal(100)


@pytest.fixture(scope="module")
def rows() -> list[SheetRow]:
    return load_rows()


@pytest.fixture(scope="module")
def compared(rows) -> list[SheetRow]:
    return split_rows(rows)[0]


@pytest.fixture(scope="module")
def priced(compared):
    return price_rows(compared)


def _row_ids(rows: list[SheetRow]) -> list[str]:
    return [row.campaign for row in rows]


def _report(row: SheetRow, name: str, ours: Decimal | None, sheet: Decimal) -> str:
    return f"{row.campaign} (row {row.number}): {name} ours={ours} sheet={sheet} difference={None if ours is None else ours - sheet}"


# ---------------------------------------------------------------- what is compared

def test_the_sheet_is_what_the_acceptance_test_expects(rows):
    assert len(rows) > 0
    assert all(row.sale >= 0 and row.served_impressions >= 0 for row in rows)


def test_the_rows_left_out_are_exactly_those_with_no_contracted_volume(rows):
    compared, excluded = split_rows(rows)

    assert {row.number for row in excluded} == {row.number for row in rows if row.oc_impressions == 0}
    assert all(row.oc_impressions > 0 for row in compared)
    assert {row.number for row in compared} | {row.number for row in excluded} == {row.number for row in rows}
    assert not {row.number for row in compared} & {row.number for row in excluded}
    assert "sin volumen contratado" in EXCLUDED_REASON and "entrega sin casar" in EXCLUDED_REASON


def test_the_cost_of_the_rows_left_out_makes_the_difference_with_the_sheet_explicit(rows, record_property):
    compared, excluded = split_rows(rows)
    excluded_cost = sum((row.total_cost for row in excluded), Decimal(0))
    components = sum((row.purchase_cost + row.sheet_rebate + row.sheet_platform_cost for row in excluded), Decimal(0))
    sheet_total_margin = sum((row.margin for row in rows), Decimal(0))
    compared_margin = sum((row.margin for row in compared), Decimal(0))
    excluded_margin = sum((row.margin for row in excluded), Decimal(0))
    record_property("excluded_rows", [row.campaign for row in excluded])
    record_property("excluded_total_cost", str(excluded_cost))
    record_property("sheet_margin_all_rows", str(sheet_total_margin))
    record_property("sheet_margin_compared_rows", str(compared_margin))
    print(f"\n[acceptance] rows left out: {len(excluded)} ({EXCLUDED_REASON}); their total cost: {excluded_cost}; "
          f"sheet margin over all rows: {sheet_total_margin}, over the compared rows: {compared_margin}")

    # The sheet's total margin is the compared rows' plus the excluded rows', which have cost and no sale.
    assert sheet_total_margin == compared_margin + excluded_margin
    assert all(row.sale == 0 for row in excluded)
    assert excluded_margin == -excluded_cost
    assert abs(components - excluded_cost) <= CENT * max(len(excluded), 1)
    assert sheet_total_margin - compared_margin == -excluded_cost


# ---------------------------------------------------------------- row by row

def test_every_compared_row_was_priced(compared, priced):
    assert set(priced) == {row.number for row in compared}


def test_each_amount_of_each_row_matches_the_sheet(compared, priced):
    failures: list[str] = []
    for row in compared:
        margin = priced[row.number].margin
        checks = [
            ("revenue", margin.revenue, row.sale, CENT),
            ("media cost", margin.media_cost, row.purchase_cost, CENT),
            ("rebate", margin.rebate, row.sheet_rebate, CENT),
            ("platform cost", margin.platform_cost, row.sheet_platform_cost, CENT),
            ("margin", margin.margin, row.margin, MARGIN_TOLERANCE),
        ]
        failures += [
            _report(row, name, ours, sheet) for name, ours, sheet, tolerance in checks if abs(ours - sheet) > tolerance
        ]
    assert not failures, "\n".join(failures)


def test_each_margin_percentage_matches_the_sheet_in_points(compared, priced):
    failures: list[str] = []
    for row in compared:
        ours = priced[row.number].margin.margin_pct
        if row.sale == 0 or row.margin_pct is None:
            if ours is not None:
                failures.append(f"{row.campaign} (row {row.number}): margin_pct ours={ours}, the sheet has none")
            continue
        sheet = row.margin_pct * HUNDRED
        if ours is None or abs(ours - sheet) > PCT_TOLERANCE:
            failures.append(_report(row, "margin_pct", ours, sheet))
    assert not failures, "\n".join(failures)


def test_a_row_is_below_cost_exactly_when_the_sheet_margin_is_negative(compared, priced):
    ours = {row.number for row in compared if priced[row.number].margin.below_cost}
    sheet = {row.number for row in compared if row.margin < 0}

    assert ours == sheet, f"ours only: {sorted(ours - sheet)}, sheet only: {sorted(sheet - ours)}"


# ---------------------------------------------------------------- aggregate over the compared rows

@pytest.fixture(scope="module")
def totals(compared, priced):
    return total_flights(priced[row.number].margin for row in compared)


def _sum(compared, attribute) -> Decimal:
    return sum((attribute(row) for row in compared), Decimal(0))


def test_the_sum_of_margins_matches_the_sheet(compared, totals):
    sheet = _sum(compared, lambda row: row.margin)

    assert abs(totals.margin - sheet) <= AGGREGATE_TOLERANCE, f"ours={totals.margin} sheet={sheet}"


def test_the_margin_on_total_sales_matches_the_sheet(compared, totals):
    sheet = _sum(compared, lambda row: row.margin) / _sum(compared, lambda row: row.sale) * HUNDRED

    assert abs(totals.margin_pct - sheet) <= AGGREGATE_PCT_TOLERANCE, f"ours={totals.margin_pct} sheet={sheet}"


def test_the_margin_without_platform_matches_the_sheet(compared, totals):
    sales = _sum(compared, lambda row: row.sale)
    sheet = (sales - _sum(compared, lambda row: row.purchase_cost) - _sum(compared, lambda row: row.sheet_rebate)) / sales * HUNDRED
    ours = (totals.revenue - totals.media_cost - totals.rebate) / totals.revenue * HUNDRED

    assert abs(ours - sheet) <= AGGREGATE_PCT_TOLERANCE, f"ours={ours} sheet={sheet}"


def test_the_gap_between_the_two_margins_is_the_platform_cost_over_sales(compared, totals):
    sales = _sum(compared, lambda row: row.sale)
    sheet_gap = _sum(compared, lambda row: row.sheet_platform_cost) / sales * HUNDRED
    without_platform = (totals.revenue - totals.media_cost - totals.rebate) / totals.revenue * HUNDRED
    ours_gap = without_platform - totals.margin_pct

    assert abs(ours_gap - sheet_gap) <= AGGREGATE_PCT_TOLERANCE, f"ours={ours_gap} sheet={sheet_gap}"
    assert abs(ours_gap - totals.platform_cost / totals.revenue * HUNDRED) <= AGGREGATE_PCT_TOLERANCE


def test_the_number_of_negative_margin_flights_matches_the_sheet(compared, totals):
    assert totals.below_cost_count == sum(1 for row in compared if row.margin < 0)
