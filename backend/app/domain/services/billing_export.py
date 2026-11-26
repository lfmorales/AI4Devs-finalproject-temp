"""The CSV of a closed month's billing, written so that Excel set to Spanish opens it in columns
(finance/billing-report)."""

import csv
import io
from collections.abc import Sequence
from decimal import Decimal

from app.domain.value_objects.billing import BillingBasis
from app.domain.value_objects.billing_export import ExportRow

HEADER = (
    "cliente", "agencia", "campaña", "línea", "orden de compra", "entregado", "contratado", "arrastre", "facturable",
    "CPM", "importe", "ajustado", "motivo",
)
_BYTE_ORDER_MARK = "﻿"
_ADJUSTED_BASES = frozenset({BillingBasis.DELIVERED, BillingBasis.CONTRACTED, BillingBasis.CUSTOM})
_FOUR_PLACES = Decimal("0.0001")
_TWO_PLACES = Decimal("0.01")


def export_file_name(year: int, month: int) -> str:
    return f"facturacion-{year}-{month:02d}.csv"


def billing_csv(rows: Sequence[ExportRow]) -> bytes:
    """UTF-8 with a byte order mark, `;` between fields, a decimal comma and no thousands separator, CRLF line ends and
    RFC 4180 quoting: a field that holds the separator, a quote or a line end is quoted."""
    text = io.StringIO()
    writer = csv.writer(text, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(HEADER)
    for row in rows:
        adjusted = row.billing_basis in _ADJUSTED_BASES
        writer.writerow((
            row.advertiser, row.agency, row.campaign, str(row.line_number), row.purchase_order or "",
            _decimal(row.delivered, _FOUR_PLACES), str(row.contracted),
            "" if row.carryover is None else str(row.carryover),
            "" if row.billable is None else _decimal(row.billable, _FOUR_PLACES),
            _decimal(row.sale_cpm, _TWO_PLACES), _decimal(row.revenue, _TWO_PLACES),
            "sí" if adjusted else "no", (row.reason or "") if adjusted else "",
        ))
    return (_BYTE_ORDER_MARK + text.getvalue()).encode("utf-8")


def _decimal(value: Decimal, places: Decimal) -> str:
    """A decimal comma and no thousands separator: 3500,00, never 3500.00 or 3.500,00."""
    return format(value.quantize(places), "f").replace(".", ",")
