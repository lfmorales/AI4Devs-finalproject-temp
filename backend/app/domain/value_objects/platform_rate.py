from dataclasses import dataclass
from datetime import datetime
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


@dataclass(frozen=True)
class NewPlatformRateSetting:
    """A platform rate to store. Exactly the key of its level is set; the system level has none."""

    level: PlatformRateLevel
    rate_per_thousand: Decimal
    created_by: int
    campaign_line_id: int | None = None
    agency_id: int | None = None
    campaign_type_id: int | None = None


@dataclass(frozen=True)
class PlatformRateSetting:
    setting_id: int
    level: PlatformRateLevel
    rate_per_thousand: Decimal
    created_by: int | None
    created_at: datetime
    campaign_line_id: int | None
    agency_id: int | None
    campaign_type_id: int | None
