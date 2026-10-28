from decimal import Decimal

from app.domain.value_objects.platform_rate import PlatformRateLevel, ResolvedPlatformRate


def _require_decimal(name: str, value: Decimal | None) -> None:
    if value is not None and not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, not {type(value).__name__}")


def resolve_platform_rate(
    *,
    system: Decimal,
    line: Decimal | None = None,
    agency: Decimal | None = None,
    campaign_type: Decimal | None = None,
) -> ResolvedPlatformRate:
    """The most specific configured rate: line, then agency, then campaign type, then system.

    An absent level is `None` and is skipped; a configured zero is a rate. The system value is data the
    caller reads from `platform_rate_settings`; nothing here knows what it is.
    """
    _require_decimal("system", system)
    _require_decimal("line", line)
    _require_decimal("agency", agency)
    _require_decimal("campaign_type", campaign_type)
    if line is not None:
        return ResolvedPlatformRate(line, PlatformRateLevel.LINE)
    if agency is not None:
        return ResolvedPlatformRate(agency, PlatformRateLevel.AGENCY)
    if campaign_type is not None:
        return ResolvedPlatformRate(campaign_type, PlatformRateLevel.CAMPAIGN_TYPE)
    return ResolvedPlatformRate(system, PlatformRateLevel.SYSTEM)
