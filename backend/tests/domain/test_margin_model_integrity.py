"""Properties of the whole margin model: one model for every channel, and no binary floating point anywhere."""

import ast
import dataclasses
from datetime import date
from decimal import Decimal, FloatOperation, localcontext
from pathlib import Path

import pytest

from app.domain.services import flight_margin, margin_totals
from app.domain.services.flight_margin import calculate_flight_margin
from app.domain.services.margin_totals import total_flights, total_lines
from app.domain.value_objects import margin
from app.domain.value_objects.margin import FlightEconomics

MARGIN_MODULES = (margin, flight_margin, margin_totals)
AS_OF = date(2026, 9, 10)


def _source(module: object) -> str:
    return Path(module.__file__).read_text()  # type: ignore[attr-defined]


def _flight(
    contracted_impressions: int = 726_202,
    sale_cpm: str = "5.00",
    start: date = date(2026, 8, 1),
    end: date = date(2026, 8, 31),
    rebate_amount: str = "907.7525",
) -> FlightEconomics:
    return FlightEconomics(
        flight_start=start,
        flight_end=end,
        contracted_impressions=contracted_impressions,
        sale_cpm=Decimal(sale_cpm),
        delivered_impressions=700_000,
        media_cost=Decimal("1200.00"),
        rebate_amount=Decimal(rebate_amount),
        platform_rate=Decimal("1.00"),
    )


def test_the_flight_input_carries_no_channel():
    names = {field.name for field in dataclasses.fields(FlightEconomics)}

    assert not {name for name in names if "channel" in name or "deal" in name or "platform_type" in name}


@pytest.mark.parametrize("module", MARGIN_MODULES)
def test_no_margin_module_branches_on_a_channel(module: object):
    identifiers = {
        node.id.lower() for node in ast.walk(ast.parse(_source(module))) if isinstance(node, ast.Name)
    } | {
        node.attr.lower() for node in ast.walk(ast.parse(_source(module))) if isinstance(node, ast.Attribute)
    }
    literals = {
        node.value.lower()
        for node in ast.walk(ast.parse(_source(module)))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert not any(word in name for name in identifiers | literals for word in ("deal", "directo", "channel"))


def test_a_deal_flight_and_a_directo_flight_with_the_same_numbers_have_the_same_margin():
    # The model takes no channel, so a Deal and a Directo flight are indistinguishable to it by construction.
    deal = calculate_flight_margin(_flight(), as_of=date(2026, 9, 1))
    directo = calculate_flight_margin(_flight(), as_of=date(2026, 9, 1))

    assert deal == directo
    assert deal.revenue == Decimal("3631.01")


@pytest.mark.parametrize("module", MARGIN_MODULES)
def test_no_margin_module_uses_float(module: object):
    tree = ast.parse(_source(module))

    float_constants = [node for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, float)]
    float_names = [node for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == "float"]
    floor_or_power = [node for node in ast.walk(tree) if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.FloorDiv, ast.Pow))]

    assert not float_constants
    assert not float_names
    assert not floor_or_power


def test_the_whole_calculation_runs_with_float_operations_trapped():
    with localcontext() as context:
        context.traps[FloatOperation] = True
        closed = calculate_flight_margin(_flight(), as_of=date(2026, 9, 1))
        running = calculate_flight_margin(_flight(), as_of=date(2026, 8, 10))
        total_lines([total_flights([closed, running])])


def test_every_amount_of_every_state_is_a_decimal():
    results = [
        calculate_flight_margin(_flight(), as_of=date(2026, 9, 1)),
        calculate_flight_margin(_flight(), as_of=date(2026, 8, 10)),
    ]
    totals = total_lines([total_flights(results)])

    for result in results:
        for amount in (result.revenue, result.media_cost, result.rebate, result.platform_cost, result.margin):
            assert isinstance(amount, Decimal)
    for amount in (totals.revenue, totals.media_cost, totals.rebate, totals.platform_cost, totals.margin):
        assert isinstance(amount, Decimal)


def test_a_year_of_amounts_accumulates_exactly():
    # 1,000 flights of exactly 0.10 € revenue: binary floats would sum to 99.9999999999986.
    flights = [
        calculate_flight_margin(
            _flight(contracted_impressions=1000, sale_cpm="0.10", rebate_amount="0"), as_of=date(2026, 9, 1)
        )
    ] * 1000

    total = total_flights(flights)

    assert total.revenue == Decimal("100.00")


def test_a_year_of_rebates_equals_the_sum_of_the_individual_rounded_amounts():
    monthly = calculate_flight_margin(_flight(rebate_amount="33.335"), as_of=date(2026, 9, 1))

    total = total_flights([monthly] * 12)

    assert monthly.rebate == Decimal("33.34")
    assert total.rebate == Decimal("400.08")
