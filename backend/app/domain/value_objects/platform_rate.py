from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class PlatformRateLevel(StrEnum):
    LINE = "line"
    AGENCY = "agency"
    CAMPAIGN_TYPE = "campaign_type"
    SYSTEM = "system"


@dataclass(frozen=True)
class ResolvedPlatformRate:
    """Euros per thousand delivered impressions, and the level that supplied it."""

    rate: Decimal
    level: PlatformRateLevel
