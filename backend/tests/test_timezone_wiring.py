"""The configured zone reaches the API's notion of today."""

from datetime import UTC, date, datetime

from app.config import Settings
from app.presentation.dependencies import providers

REQUIRED = {"database_url": "x", "cognito_region": "x", "cognito_user_pool_id": "x", "cognito_client_id": "x"}


def test_the_zone_defaults_to_madrid():
    assert Settings(**REQUIRED).app_timezone == "Europe/Madrid"


def test_the_zone_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("APP_TIMEZONE", "Asia/Tokyo")

    assert Settings(**REQUIRED).app_timezone == "Asia/Tokyo"


def test_the_api_takes_today_in_the_configured_zone_not_in_utc(monkeypatch):
    # 00:30 on 11 August in Madrid is still the 10th in UTC.
    monkeypatch.setattr(providers, "_utc_now", lambda: datetime(2026, 8, 10, 22, 30, tzinfo=UTC))
    monkeypatch.setattr(providers, "get_settings", lambda: Settings(**REQUIRED))

    assert providers.get_today() == date(2026, 8, 11)
