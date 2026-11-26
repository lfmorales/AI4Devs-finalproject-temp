import pytest
from decimal import Decimal

from app.domain.value_objects.contracted_volume import ContractedVolume


def test_contracted_volume_decimal_arithmetic():
    """Test that ContractedVolume uses Decimal, never float."""
    volume = ContractedVolume(
        contracted_impressions=1_000_000,
        sale_cpm=Decimal("25.50")
    )

    # Revenue must be Decimal, not float
    revenue = volume.revenue()
    assert isinstance(revenue, Decimal)
    assert revenue == Decimal("25500.00")  # 1M * 25.50 / 1000


def test_the_contracted_sale_reads_the_contracted_volume_not_the_delivery():
    """The line's contracted sale is the purchase order's value, whatever is delivered.

    Not inverted by committed-billing-and-review: this value object has no delivery, and its figure is the contracted
    sale, not a flight's revenue, which is now its billing (tests/domain/test_billing.py).
    """
    volume = ContractedVolume(
        contracted_impressions=1_000_000,
        sale_cpm=Decimal("30.00")
    )

    # The contracted sale is 30k whatever is delivered
    revenue = volume.revenue()
    assert revenue == Decimal("30000.00")


def test_cpm_precision():
    """Test that CPM maintains precision through calculation."""
    volume = ContractedVolume(
        contracted_impressions=1_234_567,
        sale_cpm=Decimal("3.75")
    )

    revenue = volume.revenue()
    # 1,234,567 * 3.75 / 1000 = 4,629.63..., rounded to 2 decimals
    expected = (Decimal("1234567") * Decimal("3.75") / Decimal("1000")).quantize(Decimal("0.01"))
    assert revenue == expected


def test_contracted_volume_immutable():
    """Test that ContractedVolume is immutable (frozen dataclass)."""
    volume = ContractedVolume(
        contracted_impressions=100_000,
        sale_cpm=Decimal("10.00")
    )

    with pytest.raises(AttributeError):
        volume.contracted_impressions = 200_000
