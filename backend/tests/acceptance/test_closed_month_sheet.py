"""Acceptance of the closed month: the domain against the private sheet, row by row and in aggregate.

Nothing here knows a figure of the sheet: it reads the sheet and compares. A row that does not match is
reported with its numbers, never fixed by touching the code.

Known difference with the sheet (committed-billing-and-review, confirmed by the business on 2026-11-26). The sheet
bills every row its whole contracted volume; a committed flight now earns its billing, the lesser of served and
contracted. The expected figures are the sheet's own columns with that rule applied (`expected_revenue`,
`expected_rebate`, `expected_margin` in closed_month_sheet.py), and the rows that served at least their volume still
match the sheet's sale, rebate, margin and percentage. On the sheet of 2026-11-26 this moves exactly 10 of the 51 rows
compared, every one of them a row that served less than it contracted (Campaign 8, 10, 28, 37, 42, 47, 50, 51, 52 and
53): their revenue goes down by 1,258.41 € and their margin by 1,040.18 € against the contracted sale the domain billed
before, every amount rounded to the cent as the margin rounds it (1,258.38 € and 1,040.19 € against the sheet's own
unrounded columns), and the margin over total revenue of the compared rows goes from 37.55 % to 37.22 %. The number of
rows with a negative margin stays 1. The two tests under «the known difference with the sheet» check it and record both
figures with `record_property`.
"""

from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal

import pytest

from app.domain.services.margin_totals import total_flights
from app.domain.value_objects.margin import MarginTotals
from app.domain.value_objects.priced_flight import PricedFlight
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


def test_each_amount_of_each_row_matches_the_sheet_billed_at_the_lesser_of_served_and_contracted(compared, priced):
    failures: list[str] = []
    for row in compared:
        margin = priced[row.number].margin
        checks = [
            ("revenue", margin.revenue, row.expected_revenue, CENT),
            ("media cost", margin.media_cost, row.purchase_cost, CENT),
            ("rebate", margin.rebate, row.expected_rebate, CENT),
            ("platform cost", margin.platform_cost, row.sheet_platform_cost, CENT),
            ("margin", margin.margin, row.expected_margin, MARGIN_TOLERANCE),
        ]
        failures += [
            _report(row, name, ours, sheet) for name, ours, sheet, tolerance in checks if abs(ours - sheet) > tolerance
        ]
    assert not failures, "\n".join(failures)


def test_each_margin_percentage_matches_the_sheet_billed_at_the_lesser_in_points(compared, priced):
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


def test_the_rows_whose_billing_departs_from_the_sheet_are_exactly_those_that_served_less_than_they_contracted(
    compared: list[SheetRow], priced: dict[int, PricedFlight], record_property: Callable[[str, object], None]
) -> None:
    departing = [row for row in compared if abs(row.expected_revenue - row.sale) > CENT]
    under_delivered = [row for row in compared if row.served_less_than_contracted and row.oc_cpm > 0]
    record_property("rows_billed_below_the_sheet", [row.campaign for row in departing])
    print(f"\n[acceptance] rows billed below the sheet's sale: {len(departing)} of {len(compared)}: "
          f"{', '.join(row.campaign for row in departing)}")

    assert {row.number for row in departing} == {row.number for row in under_delivered}
    assert all(row.expected_revenue < row.sale for row in departing)
    # The others still match the sheet itself, not only the rule applied to it.
    failures: list[str] = []
    for row in compared:
        if row in departing:
            continue
        margin = priced[row.number].margin
        for name, ours, sheet, tolerance in (
            ("revenue", margin.revenue, row.sale, CENT),
            ("rebate", margin.rebate, row.sheet_rebate, CENT),
            ("margin", margin.margin, row.margin, MARGIN_TOLERANCE),
        ):
            if ours is None or abs(ours - sheet) > tolerance:
                failures.append(_report(row, name, ours, sheet))
    assert not failures, "\n".join(failures)


def _cent(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def _contracted_sale(row: SheetRow) -> Decimal:
    """What the domain billed the row before committed-billing-and-review: its contracted volume, rounded once."""
    return _cent(Decimal(row.contracted_impressions) / Decimal(1000) * row.oc_cpm)


def test_the_known_difference_with_the_sheet_is_recorded(
    compared: list[SheetRow], totals: MarginTotals, record_property: Callable[[str, object], None]
) -> None:
    # Against the contracted sale, every amount rounded to the cent as the margin rounds it.
    revenue_change = _sum(compared, lambda row: row.expected_revenue - _contracted_sale(row))
    margin_change = _sum(compared, lambda row: (row.expected_revenue - _contracted_sale(row)) - (
        _cent(row.expected_rebate) - _cent((row.rebate_rate or Decimal(0)) * _contracted_sale(row))))
    record_property("revenue_change_against_the_contracted_sale", str(revenue_change))
    record_property("margin_change_against_the_contracted_sale", str(margin_change))
    print(f"\n[acceptance] against the contracted sale billed before: revenue {revenue_change}, margin {margin_change}")
    # Against the sheet's own unrounded columns.
    sheet_revenue = _sum(compared, lambda row: row.sale)
    sheet_margin = _sum(compared, lambda row: row.margin)
    revenue_difference = totals.revenue - sheet_revenue
    margin_difference = totals.margin - sheet_margin
    sheet_pct = sheet_margin / sheet_revenue * HUNDRED
    record_property("revenue_difference", str(revenue_difference))
    record_property("margin_difference", str(margin_difference))
    record_property("margin_pct_sheet", str(sheet_pct.quantize(CENT)))
    record_property("margin_pct_ours", str(totals.margin_pct))
    print(f"[acceptance] against the sheet's columns: revenue {revenue_difference.quantize(CENT)}, margin "
          f"{margin_difference.quantize(CENT)}, margin over revenue {sheet_pct.quantize(CENT)} % -> {totals.margin_pct} %")

    assert revenue_difference == _sum(compared, lambda row: row.expected_revenue - row.sale)
    assert revenue_change < 0 and margin_change < 0
    assert revenue_difference < 0 and margin_difference < 0
    assert totals.margin_pct is not None and totals.margin_pct < sheet_pct
    assert totals.below_cost_count == sum(1 for row in compared if row.margin < 0)


# ---------------------------------------------------------------- aggregate over the compared rows

@pytest.fixture(scope="module")
def totals(compared, priced):
    return total_flights(priced[row.number].margin for row in compared)


def _sum(compared, attribute) -> Decimal:
    return sum((attribute(row) for row in compared), Decimal(0))


def test_the_sum_of_margins_matches_the_sheet_billed_at_the_lesser(compared, totals):
    expected = _sum(compared, lambda row: row.expected_margin)

    assert abs(totals.margin - expected) <= AGGREGATE_TOLERANCE, f"ours={totals.margin} expected={expected}"


def test_the_margin_on_total_sales_matches_the_sheet_billed_at_the_lesser(compared, totals):
    expected = _sum(compared, lambda row: row.expected_margin) / _sum(compared, lambda row: row.expected_revenue) * HUNDRED

    assert abs(totals.margin_pct - expected) <= AGGREGATE_PCT_TOLERANCE, f"ours={totals.margin_pct} expected={expected}"


def test_the_margin_without_platform_matches_the_sheet_billed_at_the_lesser(compared, totals):
    sales = _sum(compared, lambda row: row.expected_revenue)
    expected = (sales - _sum(compared, lambda row: row.purchase_cost) - _sum(compared, lambda row: row.expected_rebate)) / sales * HUNDRED
    ours = (totals.revenue - totals.media_cost - totals.rebate) / totals.revenue * HUNDRED

    assert abs(ours - expected) <= AGGREGATE_PCT_TOLERANCE, f"ours={ours} expected={expected}"


def test_the_gap_between_the_two_margins_is_the_platform_cost_over_sales(compared, totals):
    sales = _sum(compared, lambda row: row.expected_revenue)
    expected_gap = _sum(compared, lambda row: row.sheet_platform_cost) / sales * HUNDRED
    without_platform = (totals.revenue - totals.media_cost - totals.rebate) / totals.revenue * HUNDRED
    ours_gap = without_platform - totals.margin_pct

    assert abs(ours_gap - expected_gap) <= AGGREGATE_PCT_TOLERANCE, f"ours={ours_gap} expected={expected_gap}"
    assert abs(ours_gap - totals.platform_cost / totals.revenue * HUNDRED) <= AGGREGATE_PCT_TOLERANCE


def test_the_number_of_negative_margin_flights_matches_the_sheet(compared, totals):
    assert totals.below_cost_count == sum(1 for row in compared if row.expected_margin < 0)
    assert totals.below_cost_count == sum(1 for row in compared if row.margin < 0)
