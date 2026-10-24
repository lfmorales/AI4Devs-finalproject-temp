from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration read from environment variables. There are no defaults for secrets."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    database_url: str
    cognito_region: str
    cognito_user_pool_id: str
    cognito_client_id: str
    # Optional so the application starts without a DSP; a connector that needs them reports it is not configured.
    adform_client_id: str | None = None
    adform_client_secret: SecretStr | None = None

    @property
    def cognito_issuer(self) -> str:
        return f"https://cognito-idp.{self.cognito_region}.amazonaws.com/{self.cognito_user_pool_id}"

    @property
    def cognito_jwks_url(self) -> str:
        return f"{self.cognito_issuer}/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
