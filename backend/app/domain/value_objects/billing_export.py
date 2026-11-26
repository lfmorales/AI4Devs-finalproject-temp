from dataclasses import dataclass
from decimal import Decimal

from app.domain.value_objects.billing import BillingBasis


@dataclass(frozen=True)
class ExportRow:
    """One flight a closing froze, as the CSV of its month needs it: the names as stored now, every figure as the
    snapshot froze it, and the reason of the adjustment it froze. A snapshot written before the billing was frozen has
    no carry-over, billable volume or basis."""

    advertiser: str
    agency: str
    campaign: str
    line_number: int
    purchase_order: str | None
    delivered: Decimal
    contracted: int
    carryover: int | None
    billable: Decimal | None
    sale_cpm: Decimal
    revenue: Decimal
    billing_basis: BillingBasis | None
    reason: str | None
