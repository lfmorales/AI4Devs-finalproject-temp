from decimal import Decimal

from app.domain.exceptions import RebateRuleError
from app.domain.value_objects.rebate import Bracket, BracketBreakdown, BracketCharge


def apply_brackets(brackets: tuple[Bracket, ...], position_before: Decimal, revenue: Decimal) -> BracketBreakdown:
    """Charge a flight's revenue marginally: the slice from `position_before` to `position_before + revenue`.

    Each bracket takes the part of the slice inside [lower, upper). The rebate is the exact sum of
    amount times rate, unrounded; the margin calculation rounds it once.
    """
    for name, value in (("position_before", position_before), ("revenue", revenue)):
        if not isinstance(value, Decimal):
            raise TypeError(f"{name} must be a Decimal, not {type(value).__name__}")
    if revenue < 0 or position_before < 0:
        raise RebateRuleError("revenue_must_not_be_negative", "revenue and counter position must not be negative")

    slice_end = position_before + revenue
    charges: list[BracketCharge] = []
    for bracket in brackets:
        top = slice_end if bracket.upper is None else min(bracket.upper, slice_end)
        amount = top - max(bracket.lower, position_before)
        if amount > 0:
            charges.append(BracketCharge(bracket.lower, bracket.upper, bracket.rate, amount, amount * bracket.rate))
    rebate = sum((charge.rebate for charge in charges), Decimal(0))
    effective_rate = rebate / revenue if revenue > 0 else Decimal(0)
    return BracketBreakdown(tuple(charges), rebate, effective_rate)
