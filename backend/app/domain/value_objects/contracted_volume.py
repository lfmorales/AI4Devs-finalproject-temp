from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ContractedVolume:
    """
    Immutable value object for the contracted volume and pricing of a campaign line.

    `revenue()` is the line's contracted sale: the purchase order's value, which never reads
    the delivery. It is not what a flight earns: a committed flight earns its billing, the
    lesser of delivered and contracted (committed-billing-and-review).
    """

    contracted_impressions: int
    sale_cpm: Decimal

    def __post_init__(self):
        """Validate that CPM is Decimal, not float."""
        if not isinstance(self.sale_cpm, Decimal):
            raise TypeError(f"sale_cpm must be Decimal, not {type(self.sale_cpm)}")

    def revenue(self) -> Decimal:
        """
        The contracted sale of the line.

        contracted sale = contracted_impressions * sale_cpm / 1000

        Returns Decimal rounded to 2 decimal places (EUR cents).
        """
        revenue = (
            Decimal(self.contracted_impressions) * self.sale_cpm / Decimal("1000")
        )
        return revenue.quantize(Decimal("0.01"))
