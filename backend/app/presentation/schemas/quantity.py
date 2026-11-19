from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

_FOUR_PLACES = Decimal("0.0001")

# A delivered volume leaves as a text with exactly four decimals ("95000.7500"), never as a JSON number: OTS has
# decimals and a number would pass them through a binary float.
QuantityString = Annotated[
    Decimal, PlainSerializer(lambda value: format(value.quantize(_FOUR_PLACES), "f"), return_type=str)
]

IN_DELIVERY_METRIC = "counted in the unit named by `delivery_metric`"
