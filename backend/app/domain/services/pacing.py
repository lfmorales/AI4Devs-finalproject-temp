from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction

from app.domain.value_objects.volume_commitment import VolumeCommitment

# A deviation of exactly this much is inside the threshold; only more than this is flagged.
PACING_DEVIATION_THRESHOLD = Fraction(1, 10)


class PacingStatus(StrEnum):
    ON_PACE = "on_pace"
    UNDER_DELIVERING = "under_delivering"
    OVER_DELIVERING = "over_delivering"


@dataclass(frozen=True)
class PacingResult:
    expected_impressions: Decimal
    # Signed (delivered - expected) / expected; None while nothing is expected yet.
    deviation: Decimal | None
    status: PacingStatus
    days_remaining: int

    @property
    def is_deviating(self) -> bool:
        return self.status is not PacingStatus.ON_PACE


def calculate_pacing(
    contracted_impressions: int,
    period_start: date,
    period_end: date,
    as_of: date,
    delivered: Decimal,
) -> PacingResult:
    """Compare the delivered volume with a linear delivery of the contracted volume up to and including as_of.

    The delivered volume is in the unit the channel counts (impressions or OTS) and may have decimals. Nothing
    here goes through float: the expected volume and the deviation are exact fractions, so the 10 % boundary is exact.
    """
    if period_end < period_start:
        raise ValueError(f"period_end {period_end} must not be before period_start {period_start}")
    if contracted_impressions < 0 or delivered < 0:
        raise ValueError("volumes must not be negative")

    total_days = (period_end - period_start).days + 1
    elapsed_days = min(max((as_of - period_start).days + 1, 0), total_days)
    days_remaining = total_days - elapsed_days

    # Fraction keeps the 10% boundary exact where the expected volume has no finite decimal form.
    expected = Fraction(contracted_impressions * elapsed_days, total_days)
    if expected == 0:
        return PacingResult(Decimal(0), None, PacingStatus.ON_PACE, days_remaining)

    deviation = (Fraction(delivered) - expected) / expected
    if deviation < -PACING_DEVIATION_THRESHOLD:
        status = PacingStatus.UNDER_DELIVERING
    elif deviation > PACING_DEVIATION_THRESHOLD:
        status = PacingStatus.OVER_DELIVERING
    else:
        status = PacingStatus.ON_PACE
    return PacingResult(
        expected_impressions=Decimal(expected.numerator) / Decimal(expected.denominator),
        deviation=Decimal(deviation.numerator) / Decimal(deviation.denominator),
        status=status,
        days_remaining=days_remaining,
    )


def pacing_flag(pacing: PacingResult, commitment: VolumeCommitment) -> bool:
    """Whether the daily status flags the flight: any deviation beyond the threshold for a committed volume, only
    under-delivery for a target, which the buyer may exceed. The pacing still reports the over-delivery."""
    if commitment is VolumeCommitment.TARGET:
        return pacing.status is PacingStatus.UNDER_DELIVERING
    return pacing.is_deviating
